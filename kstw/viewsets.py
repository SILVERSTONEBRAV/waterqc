from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, permissions, status
from core.permissions import ViewModelPermissions
from rest_framework.response import Response
from rest_framework.decorators import action
from .choices import WaterAnalysisState
from .models import (
    WasteWaterSamplingSite, WasteWaterSample, WasteWaterAnalysis, WasteWaterParameterResult,
    IndustrialSample, IndustrialSampleAnalysis, IndustrialSampleParameterResult,
    TreatmentPlantSample, TreatmentPlantSampleAnalysis, TreatmentPlantSampleParameterResult,
    ExhausterSample, ExhausterSampleAnalysis, ExhausterSampleParameterResult
)
from .serializers import (
    WasteWaterSamplingSiteSerializer, WasteWaterSampleSerializer, WasteWaterAnalysisSerializer, WasteWaterParameterResultSerializer,
    IndustrialSampleSerializer, IndustrialSampleAnalysisSerializer, IndustrialSampleParameterResultSerializer,
    TreatmentPlantSampleSerializer, TreatmentPlantSampleAnalysisSerializer, TreatmentPlantSampleParameterResultSerializer,
    ExhausterSampleSerializer, ExhausterSampleAnalysisSerializer, ExhausterSampleParameterResultSerializer
)
from .choices import WaterAnalysisState

AUTO_TRANSITION_RULES = {
    WaterAnalysisState.ANALYSED: WaterAnalysisState.VERIFIED,
    WaterAnalysisState.VERIFIED: WaterAnalysisState.CONFIRMED,
}

class OptionalTreatmentPlantShiftMixin:
    def perform_create(self, serializer):
        user = self.request.user
        data = serializer.validated_data

        if hasattr(serializer.Meta.model, 'treatment_plant') and not data.get('treatment_plant'):
            if user.assigned_treatment_plant:
                data['treatment_plant'] = user.assigned_treatment_plant

        if hasattr(serializer.Meta.model, 'shift') and not data.get('shift'):
            if user.assigned_shift:
                data['shift'] = user.assigned_shift

        if hasattr(serializer.Meta.model, 'operator') and 'operator' not in data:
            data['operator'] = user

        serializer.save()

    def filter_queryset(self, queryset):
        user = self.request.user

        if hasattr(queryset.model, 'treatment_plant') and user.assigned_treatment_plant:
            queryset = queryset.filter(treatment_plant=user.assigned_treatment_plant)

        if hasattr(queryset.model, 'shift') and user.assigned_shift:
            queryset = queryset.filter(shift=user.assigned_shift)

        return queryset

class AutoTransitionMixin:
    def _apply_auto_transition(self, instance, user):
        current_state = getattr(instance, 'state', None) or getattr(instance, 'status', None)
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
                        remarks=f"Auto-transitioned from {current_state} to {next_state} due to timeout."
                    )
            except Exception:
                pass

class WasteWaterSamplingSiteViewSet(OptionalTreatmentPlantShiftMixin, viewsets.ModelViewSet):
    queryset = WasteWaterSamplingSite.objects.all()
    serializer_class = WasteWaterSamplingSiteSerializer
    permission_classes = [ViewModelPermissions]

class WasteWaterSampleViewSet(OptionalTreatmentPlantShiftMixin, viewsets.ModelViewSet):
    queryset = WasteWaterSample.objects.all()
    serializer_class = WasteWaterSampleSerializer
    permission_classes = [ViewModelPermissions]

class WasteWaterAnalysisViewSet(OptionalTreatmentPlantShiftMixin, AutoTransitionMixin, viewsets.ModelViewSet):
    serializer_class = WasteWaterAnalysisSerializer
    permission_classes = [ViewModelPermissions]

    def get_queryset(self):
        return super().filter_queryset(WasteWaterAnalysis.objects.prefetch_related('logs').select_related('treatment_plant', 'operator', 'shift'))

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        for instance in queryset:
            self._apply_auto_transition(instance, request.user)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._apply_auto_transition(instance, request.user)
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[ViewModelPermissions])
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

class WasteWaterParameterResultViewSet(viewsets.ModelViewSet):
    queryset = WasteWaterParameterResult.objects.all()
    serializer_class = WasteWaterParameterResultSerializer
    permission_classes = [ViewModelPermissions]

class IndustrialSampleViewSet(OptionalTreatmentPlantShiftMixin, viewsets.ModelViewSet):
    queryset = IndustrialSample.objects.all()
    serializer_class = IndustrialSampleSerializer
    permission_classes = [ViewModelPermissions]

class IndustrialSampleAnalysisViewSet(OptionalTreatmentPlantShiftMixin, AutoTransitionMixin, viewsets.ModelViewSet):
    queryset = IndustrialSampleAnalysis.objects.all()
    serializer_class = IndustrialSampleAnalysisSerializer
    permission_classes = [ViewModelPermissions]

    @action(detail=True, methods=['post'], permission_classes=[ViewModelPermissions])
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

class IndustrialSampleParameterResultViewSet(viewsets.ModelViewSet):
    queryset = IndustrialSampleParameterResult.objects.all()
    serializer_class = IndustrialSampleParameterResultSerializer
    permission_classes = [ViewModelPermissions]

class TreatmentPlantSampleViewSet(OptionalTreatmentPlantShiftMixin, viewsets.ModelViewSet):
    queryset = TreatmentPlantSample.objects.all()
    serializer_class = TreatmentPlantSampleSerializer
    permission_classes = [ViewModelPermissions]

class TreatmentPlantSampleAnalysisViewSet(OptionalTreatmentPlantShiftMixin, AutoTransitionMixin, viewsets.ModelViewSet):
    queryset = TreatmentPlantSampleAnalysis.objects.all()
    serializer_class = TreatmentPlantSampleAnalysisSerializer
    permission_classes = [ViewModelPermissions]

    @action(detail=True, methods=['post'], permission_classes=[ViewModelPermissions])
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

class TreatmentPlantSampleParameterResultViewSet(viewsets.ModelViewSet):
    queryset = TreatmentPlantSampleParameterResult.objects.all()
    serializer_class = TreatmentPlantSampleParameterResultSerializer
    permission_classes = [ViewModelPermissions]

class ExhausterSampleViewSet(OptionalTreatmentPlantShiftMixin, viewsets.ModelViewSet):
    queryset = ExhausterSample.objects.all()
    serializer_class = ExhausterSampleSerializer
    permission_classes = [ViewModelPermissions]

class ExhausterSampleAnalysisViewSet(OptionalTreatmentPlantShiftMixin, AutoTransitionMixin, viewsets.ModelViewSet):
    queryset = ExhausterSampleAnalysis.objects.all()
    serializer_class = ExhausterSampleAnalysisSerializer
    permission_classes = [ViewModelPermissions]

    @action(detail=True, methods=['post'], permission_classes=[ViewModelPermissions])
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

class ExhausterSampleParameterResultViewSet(viewsets.ModelViewSet):
    queryset = ExhausterSampleParameterResult.objects.all()
    serializer_class = ExhausterSampleParameterResultSerializer
    permission_classes = [ViewModelPermissions]
