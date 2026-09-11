# instruments/serializers.py
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from rest_framework import serializers

# =====================================================
# Treatment Plant / Phase Short Representations
# =====================================================
class TreatmentPlantSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class TreatmentPlantPhaseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


# =====================================================
# Instrument Serializer (Gateway / PLC / Controller)
# =====================================================
class InstrumentSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    manufacturer = serializers.CharField()
    model = serializers.CharField()
    serial_number = serializers.CharField()
    protocol = serializers.CharField()
    ip_address = serializers.IPAddressField(allow_null=True)
    mac_address = serializers.CharField(allow_blank=True)
    firmware_version = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    last_seen = serializers.DateTimeField(allow_null=True)
    installed_at = serializers.DateField()
    expected_heartbeat_sec = serializers.IntegerField()
    is_active = serializers.BooleanField()

    treatment_plant = TreatmentPlantSerializer()
    phase = TreatmentPlantPhaseSerializer(allow_null=True)

    sensors = serializers.SerializerMethodField()

    def get_sensors(self, obj):
        from .models import Sensor
        active_sensors = obj.sensors.filter(is_active=True)
        return SensorSerializer(active_sensors, many=True).data


# =====================================================
# Sensor / Probe Serializer
# =====================================================
class SensorSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    stage = serializers.CharField()
    unit = serializers.CharField()
    is_primary = serializers.BooleanField()
    is_active = serializers.BooleanField()
    min_detectable = serializers.DecimalField(max_digits=10, decimal_places=3, allow_null=True)
    max_detectable = serializers.DecimalField(max_digits=10, decimal_places=3, allow_null=True)
    drift_threshold = serializers.DecimalField(max_digits=6, decimal_places=3, allow_null=True)

    parameter_name = serializers.SerializerMethodField()
    instrument_uuid = serializers.UUIDField()
    treatment_plant = TreatmentPlantSerializer()
    phase = TreatmentPlantPhaseSerializer(allow_null=True)

    def get_parameter_name(self, obj):
        return obj.parameter.name if obj.parameter else None


# =====================================================
# Online Measurement Serializer
# =====================================================
class OnlineMeasurementSerializer(serializers.Serializer):
    sensor_uuid = serializers.UUIDField(source='sensor.uuid')
    value = serializers.DecimalField(max_digits=16, decimal_places=5)
    measured_at = serializers.DateTimeField()
    received_at = serializers.DateTimeField()
    quality_flag = serializers.CharField()
    signal_strength = serializers.IntegerField(allow_null=True)
    latency_ms = serializers.IntegerField(allow_null=True)
    raw_payload = serializers.JSONField(allow_null=True)
    treatment_plant = TreatmentPlantSerializer()
    phase = TreatmentPlantPhaseSerializer(allow_null=True)


# =====================================================
# Batch Measurement Serializer (High-Throughput)
# =====================================================
class InstrumentBatchMeasurementSerializer(serializers.Serializer):
    instrument_uuid = serializers.UUIDField()
    readings = OnlineMeasurementSerializer(many=True)

    @transaction.atomic
    def create(self, validated_data):
        from .models import Instrument, OnlineMeasurement, Sensor

        instrument = Instrument.objects.get(uuid=validated_data['instrument_uuid'])
        measurements = []
        now = timezone.now()

        for r in validated_data['readings']:
            sensor = Sensor.objects.get(uuid=r['sensor_uuid'])
            measurements.append(
                OnlineMeasurement(
                    sensor=sensor,
                    value=r['value'],
                    measured_at=r['measured_at'],
                    received_at=now,
                    quality_flag=r.get('quality_flag', 'ok'),
                    signal_strength=r.get('signal_strength'),
                    latency_ms=r.get('latency_ms'),
                    raw_payload=r.get('raw_payload'),
                    treatment_plant=sensor.treatment_plant,
                    phase=sensor.phase
                )
            )

        OnlineMeasurement.objects.bulk_create(measurements, batch_size=1000)
        instrument.heartbeat()

        return {
            "instrument_uuid": instrument.uuid,
            "ingested_count": len(measurements),
            "received_at": now
        }


# =====================================================
# Derived Metric Serializer
# =====================================================
class DerivedMetricSerializer(serializers.Serializer):
    sensor_uuid = serializers.UUIDField(source='sensor.uuid')
    metric_type = serializers.CharField()
    value = serializers.DecimalField(max_digits=16, decimal_places=5)
    window_start = serializers.DateTimeField()
    window_end = serializers.DateTimeField()
    computed_at = serializers.DateTimeField()
    treatment_plant = TreatmentPlantSerializer()
    phase = TreatmentPlantPhaseSerializer(allow_null=True)


# =====================================================
# Instrument Calibration Serializer
# =====================================================
class InstrumentCalibrationSerializer(serializers.Serializer):
    instrument_uuid = serializers.UUIDField(source='instrument.uuid')
    performed_at = serializers.DateTimeField()
    performed_by = serializers.CharField()
    method = serializers.CharField()
    valid_until = serializers.DateField()
    notes = serializers.CharField(allow_blank=True)
    is_expired = serializers.SerializerMethodField()

    def get_is_expired(self, obj):
        from django.utils import timezone
        return timezone.now().date() > obj.valid_until


# =====================================================
# Sensor Health Snapshot Serializer
# =====================================================
class SensorHealthSnapshotSerializer(serializers.Serializer):
    sensor_uuid = serializers.UUIDField(source='sensor.uuid')
    health_score = serializers.DecimalField(max_digits=5, decimal_places=2)
    assessed_at = serializers.DateTimeField()
    reason = serializers.CharField(allow_blank=True)
