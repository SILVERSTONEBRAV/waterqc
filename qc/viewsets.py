from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from .models import (
    WaterAnalysis,
    TreatedWaterResult,
    ClarifiedWaterResult,
    CoagulatedWaterResult,
    RawWaterResult,
    SamplingTime,
    WaterAnalysisLog,
    WaterAnalysisState,
    NonConformity,
    NonConformityLog,
    Cause,
)
from .serializers import (
    WaterAnalysisSerializer,
    TreatedWaterResultSerializer,
    ClarifiedWaterResultSerializer,
    CoagulatedWaterResultSerializer,
    RawWaterResultSerializer,
    SamplingTimeSerializer,
    WaterAnalysisLogSerializer,
    NonConformitySerializer,
    NonConformityLogSerializer,
    CauseSerializer,
)
from sc.models import ShiftAssignment


# ---------------------------
# Auto-transition rules
# ---------------------------
AUTO_TRANSITION_RULES = {
    WaterAnalysisState.ANALYSED: WaterAnalysisState.VERIFIED,
    WaterAnalysisState.VERIFIED: WaterAnalysisState.CONFIRMED,
}


# ---------------------------
# WaterAnalysis ViewSet
# ---------------------------
class WaterAnalysisViewSet(viewsets.ModelViewSet):
    serializer_class = WaterAnalysisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        assignments = ShiftAssignment.objects.filter(user=user).select_related("shift", "treatment_plant")
        assigned_shifts = [a.shift_id for a in assignments]
        assigned_plants = [a.treatment_plant_id for a in assignments]

        queryset = WaterAnalysis.objects.filter(
            shift_id__in=assigned_shifts,
            treatment_plant_id__in=assigned_plants
        ).prefetch_related('logs', 'nonconformities').select_related('treatment_plant', 'shift')

        for analysis in queryset:
            self._apply_auto_transition(analysis, user)

        return queryset

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._apply_auto_transition(instance, request.user)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save()

    def _apply_auto_transition(self, instance, user):
        current_state = instance.state
        if current_state not in AUTO_TRANSITION_RULES:
            return

        timeout_threshold = instance.updated_at + timedelta(minutes=30)
        if timezone.now() >= timeout_threshold:
            next_state = AUTO_TRANSITION_RULES[current_state]
            try:
                with transaction.atomic():
                    instance.transition_state(
                        next_state,
                        user,
                        remarks=f"Auto-transition from {current_state} to {next_state} due to timeout."
                    )
            except Exception:
                pass  # suppress errors silently during listing

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def transition(self, request, pk=None):
        instance = self.get_object()
        new_state = request.data.get("new_state")
        remarks = request.data.get("remarks", "")

        if not new_state or new_state not in WaterAnalysisState.values:
            return Response({"detail": "Invalid state"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                instance.transition_state(new_state, request.user, remarks)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------
# Base Result ViewSet
# ---------------------------
class BaseResultViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        return self.model.objects.select_related('parameter')

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.delete()


class TreatedWaterResultViewSet(BaseResultViewSet):
    queryset = TreatedWaterResult.objects.all()
    serializer_class = TreatedWaterResultSerializer
    model = TreatedWaterResult


class ClarifiedWaterResultViewSet(BaseResultViewSet):
    queryset = ClarifiedWaterResult.objects.all()
    serializer_class = ClarifiedWaterResultSerializer
    model = ClarifiedWaterResult


class CoagulatedWaterResultViewSet(BaseResultViewSet):
    queryset = CoagulatedWaterResult.objects.all()
    serializer_class = CoagulatedWaterResultSerializer
    model = CoagulatedWaterResult


class RawWaterResultViewSet(BaseResultViewSet):
    queryset = RawWaterResult.objects.all()
    serializer_class = RawWaterResultSerializer
    model = RawWaterResult


# ---------------------------
# NonConformity & Cause ViewSets
# ---------------------------
class NonConformityViewSet(viewsets.ModelViewSet):
    serializer_class = NonConformitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return NonConformity.objects.select_related('analysis', 'triggered_by').prefetch_related('causes', 'logs')

    def perform_create(self, serializer):
        serializer.save(triggered_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save()


class CauseViewSet(viewsets.ModelViewSet):
    serializer_class = CauseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Cause.objects.select_related('created_by')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# ---------------------------
# ReadOnly ViewSets
# ---------------------------
class SamplingTimeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SamplingTime.objects.all()
    serializer_class = SamplingTimeSerializer
    permission_classes = [IsAuthenticated]


class WaterAnalysisLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WaterAnalysisLog.objects.select_related("analysis", "actor").all()
    serializer_class = WaterAnalysisLogSerializer
    permission_classes = [IsAuthenticated]


class NonConformityLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NonConformityLog.objects.select_related("nonconformity", "actor").all()
    serializer_class = NonConformityLogSerializer
    permission_classes = [IsAuthenticated]
