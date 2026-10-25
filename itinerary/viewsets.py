from rest_framework import viewsets, status
from core.permissions import ViewModelPermissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import (
    SamplingPlan, DynamicSamplingPoint, Itinerary, SampleCategory,
    ASSIGNMENT_STRATEGY_REGISTRY
)
from .serializers import (
    SamplingPlanSerializer, DynamicSamplingPointSerializer,
    ItinerarySerializer, SampleCategorySerializer
)

# --- SamplingPlan ViewSet ---
class SamplingPlanViewSet(viewsets.ModelViewSet):
    queryset = SamplingPlan.objects.all()
    serializer_class = SamplingPlanSerializer
    permission_classes = [ViewModelPermissions]

    @action(detail=True, methods=['post'], url_path='refresh-actuals')
    def refresh_actual_sampled_points(self, request, pk=None):
        plan = self.get_object()
        plan.refresh_actual_sampled_points()
        return Response({'message': 'Actual sampled points refreshed.', 'actual_sampled_points': plan.actual_sampled_points})

# --- DynamicSamplingPoint ViewSet ---
class DynamicSamplingPointViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DynamicSamplingPoint.objects.select_related('content_type')
    serializer_class = DynamicSamplingPointSerializer
    permission_classes = [ViewModelPermissions]

    def get_queryset(self):
        qs = super().get_queryset()
        is_active = self.request.query_params.get('is_active')
        is_sampled_this_month = self.request.query_params.get('is_sampled_this_month')
        point_type = self.request.query_params.get('point_type')

        if is_active is not None:
            qs = qs.filter(point__is_deleted=(is_active.lower() != 'true'))

        if is_sampled_this_month is not None:
            if is_sampled_this_month.lower() == 'true':
                qs = [dsp for dsp in qs if dsp.is_sampled_this_month]
            else:
                qs = [dsp for dsp in qs if not dsp.is_sampled_this_month]

        if point_type:
            qs = qs.filter(content_type__model=point_type.lower())

        return qs

# --- SampleCategory ViewSet ---
class SampleCategoryViewSet(viewsets.ModelViewSet):
    queryset = SampleCategory.objects.all()
    serializer_class = SampleCategorySerializer
    permission_classes = [ViewModelPermissions]

# --- Itinerary ViewSet ---
class ItineraryViewSet(viewsets.ModelViewSet):
    queryset = Itinerary.objects.select_related('content_type').prefetch_related('sampling_points')
    serializer_class = ItinerarySerializer
    permission_classes = [ViewModelPermissions]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        sampling_date = self.request.query_params.get('sampling_date')

        if status_filter:
            qs = qs.filter(status=status_filter)

        if sampling_date:
            qs = qs.filter(sampling_date=sampling_date)

        return qs

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.is_locked:
            raise ValidationError("Itinerary is locked and cannot be edited.")
        serializer.save()

    @transaction.atomic
    @action(detail=True, methods=['post'], url_path='assign-points')
    def assign_sampling_points(self, request, pk=None):
        itinerary = self.get_object()
        strategy_key = request.data.get('strategy')

        if itinerary.is_locked:
            return Response({'error': 'Itinerary is locked.'}, status=status.HTTP_400_BAD_REQUEST)

        if not strategy_key:
            return Response({'error': 'Assignment strategy is required.'}, status=status.HTTP_400_BAD_REQUEST)

        strategy = ASSIGNMENT_STRATEGY_REGISTRY.get(strategy_key)
        if not strategy:
            return Response({'error': f"Strategy '{strategy_key}' not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Execute Strategy
        assigned_count = strategy.assign(itinerary)

        return Response({'message': f"{assigned_count} sampling points assigned successfully."})

    @action(detail=True, methods=['post'], url_path='lock')
    def lock_itinerary(self, request, pk=None):
        itinerary = self.get_object()
        if itinerary.is_locked:
            return Response({'error': 'Itinerary is already locked.'}, status=status.HTTP_400_BAD_REQUEST)
        itinerary.lock()
        return Response({'message': 'Itinerary locked successfully.'})

    @action(detail=True, methods=['post'], url_path='complete')
    def mark_completed(self, request, pk=None):
        itinerary = self.get_object()
        if itinerary.status == 'Completed':
            return Response({'error': 'Itinerary is already completed.'}, status=status.HTTP_400_BAD_REQUEST)
        itinerary.mark_completed()

        # Optional: Auto-update SamplingPlan actuals after completion
        plan = SamplingPlan.objects.filter(
            month__year=itinerary.sampling_date.year,
            month__month=itinerary.sampling_date.month
        ).first()
        if plan:
            plan.refresh_actual_sampled_points()

        return Response({'message': 'Itinerary marked as completed.'})

