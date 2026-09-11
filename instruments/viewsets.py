import json
from decimal import Decimal
from asgiref.sync import sync_to_async
from django.utils import timezone
from django.db.models import Max, Prefetch
from django.core.exceptions import ObjectDoesNotExist

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import OrderingFilter, SearchFilter
from django_filters.rest_framework import DjangoFilterBackend

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import (
    Instrument, Sensor, OnlineMeasurement,
    DerivedMetric, InstrumentCalibration, SensorHealthSnapshot
)
from .serializers import (
    InstrumentSerializer, SensorSerializer, OnlineMeasurementSerializer,
    DerivedMetricSerializer, InstrumentCalibrationSerializer,
    InstrumentBatchMeasurementSerializer, SensorHealthSnapshotSerializer
)
from .tasks import process_sensor_measurements


# =====================================================
# Instrument ViewSet
# =====================================================
class InstrumentViewSet(viewsets.ModelViewSet):
    """CRUD + heartbeat + batch ingestion for instruments with prefetching."""
    queryset = Instrument.objects.prefetch_related(
        Prefetch('sensors', queryset=Sensor.objects.filter(is_active=True))
    ).all()
    serializer_class = InstrumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ['treatment_plant', 'phase', 'status', 'is_active']
    search_fields = ['name', 'serial_number', 'manufacturer', 'model']
    ordering_fields = ['last_seen', 'installed_at', 'name']
    ordering = ['name']

    @action(detail=True, methods=['POST'])
    async def heartbeat(self, request, pk=None):
        """Update instrument heartbeat and refresh health."""
        instrument: Instrument = self.get_object()
        await sync_to_async(instrument.heartbeat)()
        await sync_to_async(instrument.refresh_health)()
        return Response({
            "uuid": str(instrument.uuid),
            "status": instrument.status,
            "last_seen": instrument.last_seen
        })

    @action(detail=True, methods=['POST'])
    async def batch_ingest(self, request, pk=None):
        """Asynchronously ingest multiple sensor readings."""
        data = await sync_to_async(lambda: request.data.copy())()
        data['instrument_uuid'] = str(pk)

        serializer = InstrumentBatchMeasurementSerializer(data=data)
        await sync_to_async(serializer.is_valid)(raise_exception=True)

        # Pre-flag stale sensors
        for reading in serializer.validated_data.get("readings", []):
            try:
                sensor = await sync_to_async(Sensor.objects.get)(uuid=reading["sensor_uuid"])
                if sensor.instrument.is_stale():
                    reading["quality_flag"] = "stale"
            except ObjectDoesNotExist:
                reading["quality_flag"] = "invalid"

        # Enqueue Celery task for async DB insertion
        await sync_to_async(process_sensor_measurements.delay)(serializer.validated_data)

        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['GET'])
    async def latest_measurements(self, request, pk=None):
        """Return latest measurement per sensor for this instrument."""
        instrument: Instrument = self.get_object()
        sensors = await sync_to_async(list)(instrument.sensors.all())
        response = []
        for sensor in sensors:
            measurement = await sync_to_async(lambda: sensor.measurements.order_by('-measured_at').first())()
            if measurement:
                response.append(OnlineMeasurementSerializer(measurement).data)
        return Response(response)


# =====================================================
# Sensor ViewSet
# =====================================================
class SensorViewSet(viewsets.ModelViewSet):
    queryset = Sensor.objects.select_related('instrument', 'treatment_plant', 'phase').all()
    serializer_class = SensorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ['instrument', 'parameter', 'stage', 'is_active', 'is_primary']
    search_fields = ['name']
    ordering_fields = ['name', 'unit']
    ordering = ['name']

    @action(detail=True, methods=['GET'])
    async def latest_measurement(self, request, pk=None):
        sensor: Sensor = self.get_object()
        measurement = await sync_to_async(lambda: sensor.measurements.order_by('-measured_at').first())()
        if measurement:
            return Response(OnlineMeasurementSerializer(measurement).data)
        return Response({"detail": "No measurements"}, status=404)

    @action(detail=True, methods=['GET'])
    async def health_score(self, request, pk=None):
        sensor: Sensor = self.get_object()
        snapshot = await sync_to_async(lambda: sensor.health_snapshots.order_by('-assessed_at').first())()
        if snapshot:
            return Response(SensorHealthSnapshotSerializer(snapshot).data)
        return Response({"detail": "No health data"}, status=404)


# =====================================================
# OnlineMeasurement ViewSet
# =====================================================
class OnlineMeasurementViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OnlineMeasurement.objects.select_related('sensor', 'sensor__instrument').all()
    serializer_class = OnlineMeasurementSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['sensor', 'sensor__instrument', 'treatment_plant', 'phase', 'quality_flag']
    ordering_fields = ['measured_at', 'received_at', 'value']
    ordering = ['-measured_at']


# =====================================================
# DerivedMetric ViewSet
# =====================================================
class DerivedMetricViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DerivedMetric.objects.select_related('sensor', 'sensor__instrument').all()
    serializer_class = DerivedMetricSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['sensor', 'metric_type', 'treatment_plant', 'phase']
    ordering_fields = ['computed_at', 'value']
    ordering = ['-computed_at']

    @action(detail=False, methods=['GET'])
    async def latest_per_sensor(self, request):
        qs = self.queryset
        latest = await sync_to_async(lambda: qs.values('sensor').annotate(latest_time=Max('computed_at')))()
        response = []
        for item in latest:
            metric = await sync_to_async(lambda: qs.filter(sensor=item['sensor'], computed_at=item['latest_time']).first())()
            if metric:
                response.append(DerivedMetricSerializer(metric).data)
        return Response(response)


# =====================================================
# InstrumentCalibration ViewSet
# =====================================================
class InstrumentCalibrationViewSet(viewsets.ModelViewSet):
    queryset = InstrumentCalibration.objects.select_related('instrument').all()
    serializer_class = InstrumentCalibrationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['instrument', 'performed_by']
    ordering_fields = ['performed_at', 'valid_until']
    ordering = ['-performed_at']

    @action(detail=True, methods=['GET'])
    async def is_expired(self, request, pk=None):
        calibration = self.get_object()
        expired = await sync_to_async(calibration.is_expired)()
        return Response({"expired": expired})


# =====================================================
# SensorHealthSnapshot ViewSet
# =====================================================
class SensorHealthSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SensorHealthSnapshot.objects.select_related('sensor').all()
    serializer_class = SensorHealthSnapshotSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['sensor', 'health_score']
    ordering_fields = ['assessed_at', 'health_score']
    ordering = ['-assessed_at']

    @action(detail=False, methods=['GET'])
    async def latest_per_sensor(self, request):
        qs = self.queryset
        latest = await sync_to_async(lambda: qs.values('sensor').annotate(latest_time=Max('assessed_at')))()
        response = []
        for item in latest:
            snapshot = await sync_to_async(lambda: qs.filter(sensor=item['sensor'], assessed_at=item['latest_time']).first())()
            if snapshot:
                response.append(SensorHealthSnapshotSerializer(snapshot).data)
        return Response(response)


# =====================================================
# Async MQTT Consumer
# =====================================================
class MQTTConsumer(AsyncJsonWebsocketConsumer):
    """Real-time sensor ingestion & threshold alert broadcasting."""

    async def connect(self):
        await self.accept()
        await self.send_json({"status": "connected"})

    async def receive_json(self, content, **kwargs):
        """
        Payload format:
        {
            "instrument_uuid": "uuid",
            "readings": [{"sensor_uuid": "uuid", "value": 2.5, "measured_at": "..."}]
        }
        """
        try:
            await sync_to_async(process_sensor_measurements.delay)(content)
            group_name = f"instrument_{content['instrument_uuid']}"
            await self.channel_layer.group_send(
                group_name,
                {"type": "threshold.alert", "message": content}
            )
            await self.send_json({"status": "queued"})
        except Exception as e:
            await self.send_json({"status": "error", "detail": str(e)})

    async def disconnect(self, code):
        pass
