from rest_framework import viewsets, permissions, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    PhysicochemicalParameter, MicrobialParameter, HeavyMetalParameter,
    WWQParameter_qad, CWQParameter_qad, DistributionParameter_qad,
    GigiriParameter_qad, KabeteParameter_qad, CatchmentParameter_qad,
    ParameterUnit, ParameterTypeRegistry
)

from .serializers import (
    PhysicochemicalParameterSerializer, MicrobialParameterSerializer, HeavyMetalParameterSerializer,
    WWQParameterSerializer, CWQParameterSerializer, DistributionParameterSerializer,
    GigiriParameterSerializer, KabeteParameterSerializer, CatchmentParameterSerializer,
    MicrobialParameterStandardizedSerializer, ParameterUnitSerializer
)

# --- Base Parameter ViewSet ---
class BaseParameterViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'unit']
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

# --- Non-Standardized ViewSets ---
class PhysicochemicalParameterViewSet(BaseParameterViewSet):
    queryset = PhysicochemicalParameter.objects.all()
    serializer_class = PhysicochemicalParameterSerializer

class MicrobialParameterViewSet(BaseParameterViewSet):
    queryset = MicrobialParameter.objects.all()
    serializer_class = MicrobialParameterSerializer

class HeavyMetalParameterViewSet(BaseParameterViewSet):
    queryset = HeavyMetalParameter.objects.all()
    serializer_class = HeavyMetalParameterSerializer

class CatchmentParameterViewSet(BaseParameterViewSet):
    queryset = CatchmentParameter_qad.objects.all()
    serializer_class = CatchmentParameterSerializer

# --- Standardized Parameter ViewSets ---
class WWQParameterViewSet(BaseParameterViewSet):
    queryset = WWQParameter_qad.objects.all()
    serializer_class = WWQParameterSerializer

class CWQParameterViewSet(BaseParameterViewSet):
    queryset = CWQParameter_qad.objects.all()
    serializer_class = CWQParameterSerializer

class DistributionParameterViewSet(BaseParameterViewSet):
    queryset = DistributionParameter_qad.objects.all()
    serializer_class = DistributionParameterSerializer

class GigiriParameterViewSet(BaseParameterViewSet):
    queryset = GigiriParameter_qad.objects.all()
    serializer_class = GigiriParameterSerializer

class KabeteParameterViewSet(BaseParameterViewSet):
    queryset = KabeteParameter_qad.objects.all()
    serializer_class = KabeteParameterSerializer

class MicrobialParameterStandardizedViewSet(BaseParameterViewSet):
    queryset = ParameterTypeRegistry.get('Microbial').objects.all()
    serializer_class = MicrobialParameterStandardizedSerializer

# --- Units API Endpoint ---
class ParameterUnitViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        units = [{'code': choice.value, 'description': choice.label} for choice in ParameterUnit]
        return Response(units)

# --- Registry API (Optional) ---
class ParameterRegistryViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['get'])
    def list_types(self, request):
        registry = [{'key': key, 'model': cls.__name__} for key, cls in ParameterTypeRegistry._registry.items()]
        return Response(registry)
