from rest_framework import viewsets, status, filters, permissions, throttling
from core.permissions import ViewModelPermissions
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
import csv

from .models import RawWater, RawWaterAnalysis, JarTest, JarResult, JarMeasurement
from .serializers import (
    RawWaterSerializer,
    RawWaterAnalysisSerializer,
    JarTestSerializer,
    JarResultSerializer,
    JarMeasurementSerializer
)


# ============================
# Permissions & Throttling
# ============================
class BurstRateThrottle(throttling.UserRateThrottle):
    rate = '60/hour'


class IsAnalystOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.groups.filter(name='Analyst').exists()


# ============================
# Raw Water ViewSet
# ============================
class RawWaterViewSet(viewsets.ModelViewSet):
    queryset = RawWater.objects.select_related("treatment_plant").prefetch_related("analyses")
    serializer_class = RawWaterSerializer
    permission_classes = [ViewModelPermissions, IsAnalystOrReadOnly]
    throttle_classes = [BurstRateThrottle]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['treatment_plant', 'sampled_at']
    search_fields = ['treatment_plant__name']
    ordering_fields = ['sampled_at', 'coagulant_concentration_ppm']

    def perform_create(self, serializer):
        with transaction.atomic():
            instance = serializer.save()
            instance.full_clean()
            instance.save()


# ============================
# Raw Water Analysis ViewSet
# ============================
class RawWaterAnalysisViewSet(viewsets.ModelViewSet):
    queryset = RawWaterAnalysis.objects.select_related("parameter", "raw_water")
    serializer_class = RawWaterAnalysisSerializer
    permission_classes = [ViewModelPermissions]
    throttle_classes = [BurstRateThrottle]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['raw_water', 'parameter']


# ============================
# Jar Test ViewSet
# ============================
class JarTestViewSet(viewsets.ModelViewSet):
    queryset = JarTest.objects.select_related("treatment_plant", "analyst").prefetch_related(
        "jar_results__measurements"
    )
    serializer_class = JarTestSerializer
    permission_classes = [ViewModelPermissions, IsAnalystOrReadOnly]
    throttle_classes = [BurstRateThrottle]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['treatment_plant', 'test_date', 'verified_by', 'confirmed_by', 'approved_by']
    ordering_fields = ['test_date', 'created_at']
    search_fields = ['treatment_plant__name']

    def perform_create(self, serializer):
        with transaction.atomic():
            instance = serializer.save()
            instance.rank_jar_results()

    def perform_update(self, serializer):
        with transaction.atomic():
            instance = serializer.save()
            if instance.jar_results.count() == 6:
                instance.rank_jar_results()

    def _check_permissions(self, jar_test, stage):
        if stage == 'confirm' and not jar_test.verified_at:
            raise PermissionDenied("Cannot confirm before verification.")
        if stage == 'approve' and not jar_test.confirmed_at:
            raise PermissionDenied("Cannot approve before confirmation.")

    @action(detail=False, methods=['get'], url_path='export')
    def export_csv(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="jar_tests.csv"'

        writer = csv.writer(response)
        writer.writerow(['Treatment Plant', 'Test Date', 'Analyst', 'Approved', 'Dosage'])

        for obj in queryset:
            writer.writerow([
                obj.treatment_plant.name,
                obj.test_date,
                obj.analyst.get_full_name() if obj.analyst else '',
                bool(obj.approved_at),
                obj.established_dosage_mg_per_l
            ])
        return response

    @action(detail=True, methods=['get'], url_path='expected-parameters')
    def expected_parameters(self, request, pk=None):
        jar_test = self.get_object()
        param_ids = jar_test.get_expected_parameters()
        return Response({'parameters': list(param_ids)})

    @action(detail=True, methods=['get'], url_path='chart-data')
    def chart_data(self, request, pk=None):
        jar_test = self.get_object()
        labels, turbidity, color, dosage, floc_times = [], [], [], [], []

        for jar in jar_test.jar_results.all().order_by('jar_number'):
            labels.append(f"Jar {jar.jar_number}")
            dosage.append(float(jar.dosage_mg_per_l))
            floc_times.append(jar.floc_observation_seconds or 0)
            turbidity_val = color_val = None
            for m in jar.measurements.all():
                param_name = m.parameter.parameter.name.lower()  # now from CoagulatedWaterLimit
                if param_name == 'turbidity':
                    turbidity_val = float(m.value)
                if param_name == 'color':
                    color_val = float(m.value)
            turbidity.append(turbidity_val or 0)
            color.append(color_val or 0)

        return Response({
            "labels": labels,
            "datasets": [
                {"label": "Turbidity", "data": turbidity, "backgroundColor": "#4dc9f6", "type": "bar"},
                {"label": "Color", "data": color, "backgroundColor": "#f67019", "type": "bar"},
                {"label": "Dosage (mg/L)", "data": dosage, "borderColor": "#36a2eb", "type": "line", "fill": False},
                {"label": "Floc Time (s)", "data": floc_times, "borderColor": "#9966ff", "type": "line", "fill": False}
            ]
        })

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        jar_test = self.get_object()
        jar_test.verify(request.user)
        jar_test.save()
        return Response({"status": "verified"})

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        jar_test = self.get_object()
        self._check_permissions(jar_test, 'confirm')
        jar_test.confirm(request.user)
        jar_test.save()
        return Response({"status": "confirmed"})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        jar_test = self.get_object()
        self._check_permissions(jar_test, 'approve')
        jar_test.approve(request.user)
        jar_test.save()
        return Response({"status": "approved"})

    @action(detail=True, methods=['post'])
    def revert_verification(self, request, pk=None):
        jar_test = self.get_object()
        jar_test.revert_verification()
        jar_test.save()
        return Response({"status": "verification reverted"})

    @action(detail=True, methods=['post'])
    def revert_confirmation(self, request, pk=None):
        jar_test = self.get_object()
        jar_test.revert_confirmation()
        jar_test.save()
        return Response({"status": "confirmation reverted"})

    @action(detail=True, methods=['post'])
    def revert_approval(self, request, pk=None):
        jar_test = self.get_object()
        jar_test.revert_approval()
        jar_test.save()
        return Response({"status": "approval reverted"})


# ============================
# Jar Result ViewSet
# ============================
class JarResultViewSet(viewsets.ModelViewSet):
    queryset = JarResult.objects.select_related("jar_test").prefetch_related("measurements")
    serializer_class = JarResultSerializer
    permission_classes = [ViewModelPermissions]
    throttle_classes = [BurstRateThrottle]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['jar_test', 'jar_number', 'is_optimal']


# ============================
# Jar Measurement ViewSet
# ============================
class JarMeasurementViewSet(viewsets.ModelViewSet):
    queryset = JarMeasurement.objects.select_related("jar_result", "parameter")
    serializer_class = JarMeasurementSerializer
    permission_classes = [ViewModelPermissions]
    throttle_classes = [BurstRateThrottle]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['jar_result', 'parameter']
