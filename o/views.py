from rest_framework import viewsets, permissions, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework_simplejwt.authentication import JWTAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.timezone import now

from .models import *
from .serializers import *
from .utils import get_current_shift_assignment


# === BASE VIEWSET (dynamic serializers, filtering, etc) ===
class DynamicSerializerViewSet(viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]

    # Optional dynamic serializers
    list_serializer_class = None
    detail_serializer_class = None

    def get_serializer_class(self):
        if self.action == 'list' and self.list_serializer_class:
            return self.list_serializer_class
        elif self.action == 'retrieve' and self.detail_serializer_class:
            return self.detail_serializer_class
        return super().get_serializer_class()

    def get_queryset(self):
        # Default implementation, override as needed
        return self.queryset


# === MONITORING TIME ===
class MonitoringTimeViewSet(DynamicSerializerViewSet):
    queryset = MonitoringTime.objects.all().order_by('time')
    serializer_class = MonitoringTimeSerializer
    pagination_class = None


# === CHEMICAL INFRASTRUCTURE ===

class ChemicalPumpViewSet(DynamicSerializerViewSet):
    queryset = ChemicalPump.objects.select_related('phase')
    serializer_class = ChemicalPumpDetailSerializer
    list_serializer_class = ChemicalPumpListSerializer
    filterset_fields = ['phase', 'category']
    search_fields = ['name']
    ordering_fields = ['name', 'id']


class PumpStatusViewSet(DynamicSerializerViewSet):
    queryset = PumpStatus.objects.select_related('pump', 'treatment_plant', 'updated_by')
    serializer_class = PumpStatusSerializer
    filterset_fields = ['treatment_plant', 'status', 'pump']
    ordering_fields = ['created_at', 'updated_at']

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)


class ChemicalTankViewSet(DynamicSerializerViewSet):
    queryset = ChemicalTank.objects.select_related('phase')
    serializer_class = ChemicalTankDetailSerializer
    list_serializer_class = ChemicalTankListSerializer
    filterset_fields = ['phase', 'category']
    search_fields = ['name']
    ordering_fields = ['capacity_liters']


# === HOURLY USAGE RECORDS (shared logic) ===

class BaseUsageRecordViewSet(DynamicSerializerViewSet):
    def perform_create(self, serializer):
        user = self.request.user
        date = serializer.validated_data.get('date', now().date())
        shift = get_current_shift_assignment(user, date)
        serializer.save(recorded_by=user, shift_assignment=shift)


class CoagulantUsageRecordViewSet(BaseUsageRecordViewSet):
    queryset = CoagulantUsageRecord.objects.select_related('chemical', 'treatment_plant', 'phase')
    serializer_class = CoagulantUsageRecordDetailSerializer
    list_serializer_class = CoagulantUsageRecordListSerializer
    filterset_fields = ['date', 'treatment_plant', 'phase', 'monitoring_time']
    ordering_fields = ['date', 'monitoring_time']


class PHAdjusterUsageRecordViewSet(BaseUsageRecordViewSet):
    queryset = PHAdjusterUsageRecord.objects.select_related('chemical', 'treatment_plant', 'phase')
    serializer_class = PHAdjusterUsageRecordDetailSerializer
    list_serializer_class = PHAdjusterUsageRecordListSerializer
    filterset_fields = ['date', 'treatment_plant', 'phase', 'monitoring_time']
    ordering_fields = ['date', 'monitoring_time']


class DisinfectantUsageRecordViewSet(BaseUsageRecordViewSet):
    queryset = DisinfectantUsageRecord.objects.select_related('chemical', 'treatment_plant', 'phase')
    serializer_class = DisinfectantUsageRecordDetailSerializer
    list_serializer_class = DisinfectantUsageRecordListSerializer
    filterset_fields = ['date', 'treatment_plant', 'phase', 'monitoring_time']
    ordering_fields = ['date', 'monitoring_time']


# === CHEMICAL USAGE SUMMARY ===
class ChemicalUsageRecordViewSet(DynamicSerializerViewSet):
    queryset = ChemicalUsageRecord.objects.select_related('chemical', 'treatment_plant')
    serializer_class = ChemicalUsageRecordSerializer
    filterset_fields = ['treatment_plant', 'chemical', 'date_used']
    ordering_fields = ['date_used']

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)


# === RESERVOIR ===
class ReservoirViewSet(DynamicSerializerViewSet):
    queryset = Reservoir.objects.select_related('phase')
    serializer_class = ReservoirDetailSerializer
    list_serializer_class = ReservoirListSerializer
    filterset_fields = ['phase']
    search_fields = ['name']


class ReservoirLevelViewSet(DynamicSerializerViewSet):
    queryset = ReservoirLevel.objects.select_related('reservoir', 'monitoring_time')
    serializer_class = ReservoirLevelSerializer
    filterset_fields = ['reservoir', 'date', 'monitoring_time']
    ordering_fields = ['date', 'monitoring_time']

    def perform_create(self, serializer):
        serializer.save()
