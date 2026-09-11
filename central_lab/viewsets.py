from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import (
    RegionSample, FCASample, CatchmentSample, KabeteSample, GigiriSample,
    RegionSampleAnalysis, FCASampleAnalysis, CatchmentSampleAnalysis, KabeteSampleAnalysis, GigiriSampleAnalysis,
    RegionSampleParameterResult, FCASampleParameterResult, CatchmentSampleParameterResult,
    KabeteSampleParameterResult, GigiriSampleParameterResult, SampleCategory
)
from .serializers import (
    RegionSampleSerializer, FCASampleSerializer, CatchmentSampleSerializer, KabeteSampleSerializer, GigiriSampleSerializer,
    RegionSampleAnalysisSerializer, FCASampleAnalysisSerializer, CatchmentSampleAnalysisSerializer, KabeteSampleAnalysisSerializer, GigiriSampleAnalysisSerializer,
    RegionSampleParameterResultSerializer, FCASampleParameterResultSerializer, CatchmentSampleParameterResultSerializer,
    KabeteSampleParameterResultSerializer, GigiriSampleParameterResultSerializer, SampleCategorySerializer
)

class SecureDynamicModelViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def perform_destroy(self, instance):
        instance.soft_delete()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({
            'request': self.request,
            'view': self
        })
        return context

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def change_status(self, request, pk=None):
        instance = self.get_object()
        new_status = request.data.get('status')
        user = request.user
        try:
            with transaction.atomic():
                instance.change_status(new_status, user)
            return Response({'status': 'Status updated successfully.'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# --- Sample ViewSets ---
class RegionSampleViewSet(SecureDynamicModelViewSet):
    queryset = RegionSample.objects.all()
    serializer_class = RegionSampleSerializer

class FCASampleViewSet(SecureDynamicModelViewSet):
    queryset = FCASample.objects.all()
    serializer_class = FCASampleSerializer

class CatchmentSampleViewSet(SecureDynamicModelViewSet):
    queryset = CatchmentSample.objects.all()
    serializer_class = CatchmentSampleSerializer

class KabeteSampleViewSet(SecureDynamicModelViewSet):
    queryset = KabeteSample.objects.all()
    serializer_class = KabeteSampleSerializer

class GigiriSampleViewSet(SecureDynamicModelViewSet):
    queryset = GigiriSample.objects.all()
    serializer_class = GigiriSampleSerializer

# --- Analysis ViewSets ---
class RegionSampleAnalysisViewSet(SecureDynamicModelViewSet):
    queryset = RegionSampleAnalysis.objects.select_related('sample').prefetch_related('parameter_results')
    serializer_class = RegionSampleAnalysisSerializer

class FCASampleAnalysisViewSet(SecureDynamicModelViewSet):
    queryset = FCASampleAnalysis.objects.select_related('sample').prefetch_related('parameter_results')
    serializer_class = FCASampleAnalysisSerializer

class CatchmentSampleAnalysisViewSet(SecureDynamicModelViewSet):
    queryset = CatchmentSampleAnalysis.objects.select_related('sample').prefetch_related('parameter_results')
    serializer_class = CatchmentSampleAnalysisSerializer

class KabeteSampleAnalysisViewSet(SecureDynamicModelViewSet):
    queryset = KabeteSampleAnalysis.objects.select_related('sample').prefetch_related('parameter_results')
    serializer_class = KabeteSampleAnalysisSerializer

class GigiriSampleAnalysisViewSet(SecureDynamicModelViewSet):
    queryset = GigiriSampleAnalysis.objects.select_related('sample').prefetch_related('parameter_results')
    serializer_class = GigiriSampleAnalysisSerializer

# --- Parameter Result ViewSets ---
class RegionSampleParameterResultViewSet(SecureDynamicModelViewSet):
    queryset = RegionSampleParameterResult.objects.select_related('analysis', 'parameter')
    serializer_class = RegionSampleParameterResultSerializer

class FCASampleParameterResultViewSet(SecureDynamicModelViewSet):
    queryset = FCASampleParameterResult.objects.select_related('analysis', 'parameter')
    serializer_class = FCASampleParameterResultSerializer

class CatchmentSampleParameterResultViewSet(SecureDynamicModelViewSet):
    queryset = CatchmentSampleParameterResult.objects.select_related('analysis', 'parameter')
    serializer_class = CatchmentSampleParameterResultSerializer

class KabeteSampleParameterResultViewSet(SecureDynamicModelViewSet):
    queryset = KabeteSampleParameterResult.objects.select_related('analysis', 'parameter')
    serializer_class = KabeteSampleParameterResultSerializer

class GigiriSampleParameterResultViewSet(SecureDynamicModelViewSet):
    queryset = GigiriSampleParameterResult.objects.select_related('analysis', 'parameter')
    serializer_class = GigiriSampleParameterResultSerializer

# --- Sample Category ViewSet ---
class SampleCategoryViewSet(SecureDynamicModelViewSet):
    queryset = SampleCategory.objects.all()
    serializer_class = SampleCategorySerializer

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def samples(self, request, pk=None):
        category = self.get_object()
        region_samples = RegionSample.objects.filter(category=category, is_deleted=False)
        serializer = RegionSampleSerializer(region_samples, many=True)
        return Response(serializer.data)