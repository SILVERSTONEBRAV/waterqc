from rest_framework import viewsets, status, filters
from core.permissions import ViewModelPermissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction

from .models import (
    ChemicalAnalysisMethod,
    MicrobialMethod,
    WWAnalysisMethod,
    CWAnalysisMethod,
)
from .serializers import (
    ChemicalAnalysisMethodSerializer,
    MicrobialMethodSerializer,
    WWAnalysisMethodSerializer,
    CWAnalysisMethodSerializer,
)

# -------------------------
# ChemicalAnalysisMethod ViewSet
# -------------------------
class ChemicalAnalysisMethodViewSet(viewsets.ModelViewSet):
    queryset = ChemicalAnalysisMethod.objects.all()
    serializer_class = ChemicalAnalysisMethodSerializer
    permission_classes = [ViewModelPermissions]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'is_active', 'category', 'tags', 'unit', 'version',
        'rounding_mode', 'rounding_precision',
    ]
    search_fields = ['method', 'kebs_reference', 'tags', 'description', 'formula']
    ordering_fields = ['created_at', 'updated_at', 'method', 'version', 'category', 'unit']
    ordering = ['-created_at']

    def get_serializer(self, *args, **kwargs):
        fields = self.request.query_params.get('fields')
        exclude = self.request.query_params.get('exclude')
        if fields:
            kwargs['fields'] = fields.split(',')
        if exclude:
            kwargs['exclude'] = exclude.split(',')
        return self.serializer_class(*args, **kwargs, context=self.get_serializer_context())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

# -------------------------
# MicrobialMethod ViewSet
# -------------------------
class MicrobialMethodViewSet(viewsets.ModelViewSet):
    queryset = MicrobialMethod.objects.all()
    serializer_class = MicrobialMethodSerializer
    permission_classes = [ViewModelPermissions]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'status', 'version']
    search_fields = ['name', 'kebs_reference', 'confirmatory_tests', 'description']
    ordering_fields = ['created_at', 'updated_at', 'name', 'version', 'status']
    ordering = ['-created_at']

    def get_serializer(self, *args, **kwargs):
        fields = self.request.query_params.get('fields')
        exclude = self.request.query_params.get('exclude')
        if fields:
            kwargs['fields'] = fields.split(',')
        if exclude:
            kwargs['exclude'] = exclude.split(',')
        return self.serializer_class(*args, **kwargs, context=self.get_serializer_context())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='increment-version')
    @transaction.atomic
    def increment_version(self, request, pk=None):
        """
        Increment version of MicrobialMethod with optional changelog.
        """
        method = self.get_object()
        changelog = request.data.get('change_log', '')
        method.increment_version(user=request.user, changelog=changelog)
        serializer = self.get_serializer(method)
        return Response(serializer.data, status=status.HTTP_200_OK)

# -------------------------
# WWAnalysisMethod ViewSet
# -------------------------
class WWAnalysisMethodViewSet(viewsets.ModelViewSet):
    queryset = WWAnalysisMethod.objects.all()
    serializer_class = WWAnalysisMethodSerializer
    permission_classes = [ViewModelPermissions]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'version']
    search_fields = ['name', 'reference']
    ordering_fields = ['created_at', 'updated_at', 'name', 'version']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

# -------------------------
# CWAnalysisMethod ViewSet
# -------------------------
class CWAnalysisMethodViewSet(viewsets.ModelViewSet):
    queryset = CWAnalysisMethod.objects.all()
    serializer_class = CWAnalysisMethodSerializer
    permission_classes = [ViewModelPermissions]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'version']
    search_fields = ['name', 'reference']
    ordering_fields = ['created_at', 'updated_at', 'name', 'version']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
