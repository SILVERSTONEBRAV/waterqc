from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import (
    OperationStatus,
    PhaseLossRate,
    Backwashing,
    Disludging,
    PumpFlush
)

from .serializers import (
    OperationStatusSerializer,
    PhaseLossRateSerializer,
    BackwashingSerializer,
    DisludgingSerializer,
    PumpFlushSerializer
)


class OperationStatusViewSet(viewsets.ModelViewSet):
    queryset = OperationStatus.objects.all()
    serializer_class = OperationStatusSerializer
    permission_classes = [IsAuthenticated]


class PhaseLossRateViewSet(viewsets.ModelViewSet):
    queryset = PhaseLossRate.objects.select_related('phase').all()
    serializer_class = PhaseLossRateSerializer
    permission_classes = [IsAuthenticated]


class BackwashingViewSet(viewsets.ModelViewSet):
    queryset = Backwashing.objects.select_related(
        'treatment_plant', 'phase', 'filter_unit', 'performed_by', 'shift_assignment', 'status'
    ).all()
    serializer_class = BackwashingSerializer
    permission_classes = [IsAuthenticated]


class DisludgingViewSet(viewsets.ModelViewSet):
    queryset = Disludging.objects.select_related(
        'treatment_plant', 'phase', 'clarifier', 'performed_by', 'shift_assignment', 'status'
    ).all()
    serializer_class = DisludgingSerializer
    permission_classes = [IsAuthenticated]


class PumpFlushViewSet(viewsets.ModelViewSet):
    queryset = PumpFlush.objects.select_related(
        'treatment_plant', 'phase', 'chemical_pump', 'performed_by', 'shift_assignment', 'status'
    ).all()
    serializer_class = PumpFlushSerializer
    permission_classes = [IsAuthenticated]
