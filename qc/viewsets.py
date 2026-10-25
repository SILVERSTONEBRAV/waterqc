from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from django.db import transaction

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
from core.permissions import ViewModelPermissions


def user_plant_ids(user):
    if user.is_superuser:
        return None
    plant_ids = set(
        ShiftAssignment.objects.filter(user=user).values_list("treatment_plant_id", flat=True)
    )
    assigned_plant_id = getattr(user, "assigned_treatment_plant_id", None)
    if assigned_plant_id:
        plant_ids.add(assigned_plant_id)
    return plant_ids


def enforce_plant_access(user, plant_id):
    plant_ids = user_plant_ids(user)
    if plant_ids is not None and plant_id not in plant_ids:
        raise PermissionDenied("You are not assigned to this treatment plant.")


def enforce_analysis_plant_access(user, analysis):
    enforce_plant_access(user, analysis.treatment_plant_id)


# ---------------------------
# WaterAnalysis ViewSet
# ---------------------------
class WaterAnalysisViewSet(viewsets.ModelViewSet):
    serializer_class = WaterAnalysisSerializer
    permission_classes = [ViewModelPermissions]

    def get_queryset(self):
        user = self.request.user
        assignments = ShiftAssignment.objects.filter(user=user).select_related("shift", "treatment_plant")
        assigned_shifts = [a.shift_id for a in assignments]
        if user.is_superuser:
            queryset = WaterAnalysis.objects.all()
        else:
            plant_ids = user_plant_ids(user) or set()
            queryset = WaterAnalysis.objects.filter(
                treatment_plant_id__in=plant_ids,
                shift_id__in=assigned_shifts,
            )

        queryset = queryset.prefetch_related('logs', 'nonconformities').select_related('treatment_plant', 'shift')

        return queryset

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        plant = serializer.validated_data.get("treatment_plant")
        phase = serializer.validated_data.get("treatment_plant_phase")
        shift = serializer.validated_data.get("shift")
        if plant is None:
            raise PermissionDenied("A treatment plant is required.")
        enforce_plant_access(self.request.user, plant.pk)
        if phase is not None and phase.treatment_plant_id != plant.pk:
            raise PermissionDenied("The selected phase does not belong to this treatment plant.")
        if not self.request.user.is_superuser and (shift is None or not ShiftAssignment.objects.filter(
            user=self.request.user, shift=shift, treatment_plant_id=plant.pk
        ).exists()):
            raise PermissionDenied("You are not assigned to the selected shift.")
        serializer.save()

    def perform_update(self, serializer):
        plant = serializer.validated_data.get(
            "treatment_plant", serializer.instance.treatment_plant
        )
        phase = serializer.validated_data.get(
            "treatment_plant_phase", serializer.instance.treatment_plant_phase
        )
        shift = serializer.validated_data.get("shift", serializer.instance.shift)
        enforce_plant_access(self.request.user, plant.pk)
        if phase is not None and phase.treatment_plant_id != plant.pk:
            raise PermissionDenied("The selected phase does not belong to this treatment plant.")
        if not self.request.user.is_superuser and (shift is None or not ShiftAssignment.objects.filter(
            user=self.request.user, shift=shift, treatment_plant_id=plant.pk
        ).exists()):
            raise PermissionDenied("You are not assigned to the selected shift.")
        serializer.save()

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


# ---------------------------
# Base Result ViewSet
# ---------------------------
class BaseResultViewSet(viewsets.ModelViewSet):
    permission_classes = [ViewModelPermissions]
    lookup_field = 'id'

    def get_queryset(self):
        queryset = self.model.objects.select_related('parameter', 'analysis')
        plant_ids = user_plant_ids(self.request.user)
        if plant_ids is not None:
            queryset = queryset.filter(analysis__treatment_plant_id__in=plant_ids)
        return queryset

    def perform_create(self, serializer):
        enforce_analysis_plant_access(self.request.user, serializer.validated_data["analysis"])
        serializer.save()

    def perform_update(self, serializer):
        analysis = serializer.validated_data.get("analysis", serializer.instance.analysis)
        enforce_analysis_plant_access(self.request.user, analysis)
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
    permission_classes = [ViewModelPermissions]

    def get_queryset(self):
        queryset = NonConformity.objects.select_related('analysis', 'triggered_by').prefetch_related('causes', 'logs')
        plant_ids = user_plant_ids(self.request.user)
        if plant_ids is not None:
            queryset = queryset.filter(analysis__treatment_plant_id__in=plant_ids)
        return queryset

    def perform_create(self, serializer):
        enforce_analysis_plant_access(self.request.user, serializer.validated_data["analysis"])
        serializer.save(triggered_by=self.request.user)

    def perform_update(self, serializer):
        analysis = serializer.validated_data.get("analysis", serializer.instance.analysis)
        enforce_analysis_plant_access(self.request.user, analysis)
        serializer.save()


class CauseViewSet(viewsets.ModelViewSet):
    serializer_class = CauseSerializer
    permission_classes = [ViewModelPermissions]

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
    permission_classes = [ViewModelPermissions]


class WaterAnalysisLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WaterAnalysisLog.objects.select_related("analysis", "actor").all()
    serializer_class = WaterAnalysisLogSerializer
    permission_classes = [ViewModelPermissions]

    def get_queryset(self):
        queryset = super().get_queryset()
        plant_ids = user_plant_ids(self.request.user)
        if plant_ids is not None:
            queryset = queryset.filter(analysis__treatment_plant_id__in=plant_ids)
        return queryset


class NonConformityLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NonConformityLog.objects.select_related("nonconformity", "actor").all()
    serializer_class = NonConformityLogSerializer
    permission_classes = [ViewModelPermissions]

    def get_queryset(self):
        queryset = super().get_queryset()
        plant_ids = user_plant_ids(self.request.user)
        if plant_ids is not None:
            queryset = queryset.filter(nonconformity__analysis__treatment_plant_id__in=plant_ids)
        return queryset
