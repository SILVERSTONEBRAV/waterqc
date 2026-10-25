from rest_framework import viewsets, status, filters, permissions, throttling
from core.permissions import ViewModelPermissions
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
import csv

from .models import PHAdjustmentTest, PHAdjustmentJarResult
from .serializers import (
    PHAdjustmentTestDetailSerializer,
    PHAdjustmentTestWriteSerializer,
    PHAdjustmentTestListSerializer,
    PHAdjustmentJarResultSerializer,
)


# ======================
# Throttle and Permissions
# ======================
class BurstRateThrottle(throttling.UserRateThrottle):
    rate = '60/hour'


class IsAnalystOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.groups.filter(name='Analyst').exists()


# ======================
# PHAdjustmentTest ViewSet
# ======================
class PHAdjustmentTestViewSet(viewsets.ModelViewSet):
    queryset = PHAdjustmentTest.objects.select_related(
        "treatment_plant", "analyst",
        "verified_by", "confirmed_by", "approved_by"
    ).prefetch_related("jar_results")

    permission_classes = [ViewModelPermissions, IsAnalystOrReadOnly]
    throttle_classes = [BurstRateThrottle]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['treatment_plant', 'test_date', 'verified_by', 'confirmed_by', 'approved_by']
    ordering_fields = ['test_date', 'created_at']
    ordering = ['-test_date']

    def get_serializer_class(self):
        if self.action == 'list':
            return PHAdjustmentTestListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return PHAdjustmentTestWriteSerializer
        return PHAdjustmentTestDetailSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
            test = serializer.save()
            test.rank_results()

    def perform_update(self, serializer):
        with transaction.atomic():
            test = serializer.save()
            test.rank_results()

    def _check_permissions(self, obj, stage):
        if stage == 'confirm' and not obj.verified_at:
            raise PermissionDenied("Verify before confirming.")
        if stage == 'approve' and not obj.confirmed_at:
            raise PermissionDenied("Confirm before approving.")

    # === Review Actions ===
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        test = self.get_object()
        test.verify(request.user)
        test.save()
        return Response({"status": "verified"})

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        test = self.get_object()
        self._check_permissions(test, 'confirm')
        test.confirm(request.user)
        test.save()
        return Response({"status": "confirmed"})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        test = self.get_object()
        self._check_permissions(test, 'approve')
        test.approve(request.user)
        test.save()
        return Response({"status": "approved"})

    @action(detail=True, methods=['post'])
    def revert_verification(self, request, pk=None):
        test = self.get_object()
        test.revert_verification()
        test.save()
        return Response({"status": "verification reverted"})

    @action(detail=True, methods=['post'])
    def revert_confirmation(self, request, pk=None):
        test = self.get_object()
        test.revert_confirmation()
        test.save()
        return Response({"status": "confirmation reverted"})

    @action(detail=True, methods=['post'])
    def revert_approval(self, request, pk=None):
        test = self.get_object()
        test.revert_approval()
        test.save()
        return Response({"status": "approval reverted"})

    # === Export CSV ===
    @action(detail=False, methods=['get'], url_path='export')
    def export_csv(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="ph_adjustment_tests.csv"'

        writer = csv.writer(response)
        writer.writerow(['Treatment Plant', 'Test Date', 'Analyst', 'Approved?', 'Dosage (mg/L)'])

        for obj in queryset:
            writer.writerow([
                obj.treatment_plant.name,
                obj.test_date,
                obj.analyst.full_name if obj.analyst else '—',
                "Yes" if obj.approved_at else "No",
                obj.established_dosage_mg_per_l or 'N/A'
            ])
        return response

    # === Chart Data for Frontend
    @action(detail=True, methods=['get'], url_path='chart-data')
    def chart_data(self, request, pk=None):
        test = self.get_object()
        jars = test.jar_results.order_by('jar_number')

        return Response({
            "labels": [f"Jar {j.jar_number}" for j in jars],
            "datasets": [
                {
                    "label": "Dosage (mg/L)",
                    "data": [float(j.dosage_mg_per_l) for j in jars],
                    "backgroundColor": "#4bc0c0",
                    "type": "bar"
                },
                {
                    "label": "Final pH",
                    "data": [float(j.final_ph or 0) for j in jars],
                    "borderColor": "#ff6384",
                    "type": "line",
                    "fill": False
                }
            ]
        })


# ======================
# PHAdjustmentJarResult ViewSet
# ======================
class PHAdjustmentJarResultViewSet(viewsets.ModelViewSet):
    queryset = PHAdjustmentJarResult.objects.select_related("test")
    serializer_class = PHAdjustmentJarResultSerializer
    permission_classes = [ViewModelPermissions]
    throttle_classes = [BurstRateThrottle]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['test', 'jar_number', 'is_optimal']
