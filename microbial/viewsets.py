from rest_framework import viewsets, status
from core.permissions import ViewModelPermissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    MicrobialAnalysis,
    MicrobialMethod,
    MicrobialParameterResult,
    TreatedWaterParameterResult,
)

from.serializers import (
    MicrobialAnalysisSerializer,
    MicrobialMethodSerializer,
    MicrobialParameterResultSerializer,
    TreatedWaterParameterResultSerializer,
    MicrobialAnalysisStateTransitionSerializer,
)

from django.shortcuts import get_object_or_404


class MicrobialMethodViewSet(viewsets.ModelViewSet):
    queryset = MicrobialMethod.objects.all()
    serializer_class = MicrobialMethodSerializer
    permission_classes = [ViewModelPermissions]


class MicrobialParameterResultViewSet(viewsets.ModelViewSet):
    queryset = MicrobialParameterResult.objects.select_related('parameter', 'analysis')
    serializer_class = MicrobialParameterResultSerializer
    permission_classes = [ViewModelPermissions]

    def perform_create(self, serializer):
        serializer.save()


class TreatedWaterParameterResultViewSet(viewsets.ModelViewSet):
    queryset = TreatedWaterParameterResult.objects.select_related('parameter', 'analysis')
    serializer_class = TreatedWaterParameterResultSerializer
    permission_classes = [ViewModelPermissions]

    def perform_create(self, serializer):
        serializer.save()


class MicrobialAnalysisViewSet(viewsets.ModelViewSet):
    queryset = MicrobialAnalysis.objects.select_related(
        'method',
        'treatment_plant',
        'treatment_plant_phase',
        'created_by',
        'analysed_by',
        'verified_by',
        'confirmed_by',
        'approved_by'
    ).prefetch_related(
        'microbial_parameters__parameter',
        'treated_parameters__parameter'
    )
    serializer_class = MicrobialAnalysisSerializer
    permission_classes = [ViewModelPermissions]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='transition', permission_classes=[ViewModelPermissions])
    def transition_state(self, request, pk=None):
        analysis = self.get_object()
        serializer = MicrobialAnalysisStateTransitionSerializer(
            data=request.data,
            context={'analysis': analysis, 'request': request}
        )
        if serializer.is_valid():
            return Response({'detail': 'State transitioned successfully.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
