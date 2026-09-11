from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import (
    WasteWaterSamplingSite, WasteWaterSample, WasteWaterAnalysis, WasteWaterParameterResult,
    WasteWaterStabilizationPond, WasteWaterPondSamplingSite,
    WasteWaterPondSample, WasteWaterPondAnalysis, WasteWaterPondParameterResult,
    WaterAnalysisState
)
from .serializers import (
    WasteWaterSamplingSiteSerializer, WasteWaterSampleSerializer, WasteWaterAnalysisSerializer, WasteWaterParameterResultSerializer,
    WasteWaterStabilizationPondSerializer, WasteWaterPondSamplingSiteSerializer,
    WasteWaterPondSampleSerializer, WasteWaterPondAnalysisSerializer, WasteWaterPondParameterResultSerializer
)

AUTO_TRANSITION_RULES = {
    WaterAnalysisState.ANALYSED: WaterAnalysisState.VERIFIED,
    WaterAnalysisState.VERIFIED: WaterAnalysisState.CONFIRMED,
}

class OptionalTreatmentPlantShiftMixin:
    def perform_create(self, serializer):
        user = self.request.user
        data = serializer.validated_data

        if hasattr(serializer.Meta.model, 'treatment_plant') and not data.get('treatment_plant'):
            if hasattr(user, 'assigned_treatment_plant') and user.assigned_treatment_plant:
                data['treatment_plant'] = user.assigned_treatment_plant

        if hasattr(serializer.Meta.model, 'shift') and not data.get('shift'):
            if hasattr(user, 'assigned_shift') and user.assigned_shift:
                data['shift'] = user.assigned_shift

        if hasattr(serializer.Meta.model, 'operator') and 'operator' not in data:
            data['operator'] = user

        serializer.save()

    def filter_queryset(self, queryset):
        user = self.request.user

        if hasattr(queryset.model, 'treatment_plant') and hasattr(user, 'assigned_treatment_plant') and user.assigned_treatment_plant:
            queryset = queryset.filter(treatment_plant=user.assigned_treatment_plant)

        if hasattr(queryset.model, 'shift') and hasattr(user, 'assigned_shift') and user.assigned_shift:
            queryset = queryset.filter(shift=user.assigned_shift)

        return queryset


class AutoTransitionMixin:
    def _apply_auto_transition(self, instance, user):
        current_state = getattr(instance, 'status', None)
        if current_state not in AUTO_TRANSITION_RULES:
            return

        timeout_threshold = instance.updated_at + timedelta(minutes=30)
        if timezone.now() >= timeout_threshold:
            next_state = AUTO_TRANSITION_RULES[current_state]
            try:
                with transaction.atomic():
                    instance.change_status(
                        next_state,
                        user,
                        user_has_permission=True  # Auto-transitions skip permission checks
                    )
            except Exception:
                pass  # Suppress transition errors silently


# ------------------- VIEWSETS ------------------- #

class WasteWaterSamplingSiteViewSet(OptionalTreatmentPlantShiftMixin, viewsets.ModelViewSet):
    queryset = WasteWaterSamplingSite.objects.all()
    serializer_class = WasteWaterSamplingSiteSerializer
    permission_classes = [permissions.IsAuthenticated]


class WasteWaterSampleViewSet(OptionalTreatmentPlantShiftMixin, viewsets.ModelViewSet):
    queryset = WasteWaterSample.objects.select_related('sampling_site', 'shift', 'assignment', 'treatment_plant')
    serializer_class = WasteWaterSampleSerializer
    permission_classes = [permissions.IsAuthenticated]


class WasteWaterAnalysisViewSet(OptionalTreatmentPlantShiftMixin, AutoTransitionMixin, viewsets.ModelViewSet):
    serializer_class = WasteWaterAnalysisSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = WasteWaterAnalysis.objects.select_related(
            'sample', 'analysed_by', 'verified_by', 'confirmed_by', 'approved_by'
        ).prefetch_related('parameter_results')
        return self.filter_queryset(qs)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        for instance in queryset:
            self._apply_auto_transition(instance, request.user)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._apply_auto_transition(instance, request.user)
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def transition(self, request, pk=None):
        instance = self.get_object()
        new_state = request.data.get("new_state")
        remarks = request.data.get("remarks", "")

        if not new_state or new_state not in WaterAnalysisState.values:
            return Response({"detail": "Invalid state"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                instance.change_status(new_state, request.user, user_has_permission=True)
                instance.remarks = remarks
                instance.save()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


class WasteWaterParameterResultViewSet(viewsets.ModelViewSet):
    queryset = WasteWaterParameterResult.objects.select_related('analysis', 'parameter', 'analysis_method')
    serializer_class = WasteWaterParameterResultSerializer
    permission_classes = [permissions.IsAuthenticated]


class WasteWaterStabilizationPondViewSet(OptionalTreatmentPlantShiftMixin, viewsets.ModelViewSet):
    queryset = WasteWaterStabilizationPond.objects.select_related('treatment_plant')
    serializer_class = WasteWaterStabilizationPondSerializer
    permission_classes = [permissions.IsAuthenticated]


class WasteWaterPondSamplingSiteViewSet(viewsets.ModelViewSet):
    queryset = WasteWaterPondSamplingSite.objects.select_related('pond')
    serializer_class = WasteWaterPondSamplingSiteSerializer
    permission_classes = [permissions.IsAuthenticated]


class WasteWaterPondSampleViewSet(OptionalTreatmentPlantShiftMixin, viewsets.ModelViewSet):
    queryset = WasteWaterPondSample.objects.select_related('site', 'shift', 'assignment')
    serializer_class = WasteWaterPondSampleSerializer
    permission_classes = [permissions.IsAuthenticated]


class WasteWaterPondAnalysisViewSet(OptionalTreatmentPlantShiftMixin, AutoTransitionMixin, viewsets.ModelViewSet):
    serializer_class = WasteWaterPondAnalysisSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = WasteWaterPondAnalysis.objects.select_related(
            'sample', 'analysed_by', 'verified_by', 'confirmed_by', 'approved_by'
        ).prefetch_related('parameter_results')
        return self.filter_queryset(qs)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        for instance in queryset:
            self._apply_auto_transition(instance, request.user)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._apply_auto_transition(instance, request.user)
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def transition(self, request, pk=None):
        instance = self.get_object()
        new_state = request.data.get("new_state")
        remarks = request.data.get("remarks", "")

        if not new_state or new_state not in WaterAnalysisState.values:
            return Response({"detail": "Invalid state"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                instance.change_status(new_state, request.user, user_has_permission=True)
                instance.remarks = remarks
                instance.save()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


class WasteWaterPondParameterResultViewSet(viewsets.ModelViewSet):
    queryset = WasteWaterPondParameterResult.objects.select_related('analysis', 'parameter', 'analysis_method')
    serializer_class = WasteWaterPondParameterResultSerializer
    permission_classes = [permissions.IsAuthenticated]
