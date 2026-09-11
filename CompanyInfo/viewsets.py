# CompanyInfo/viewsets.py
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import CompanyInfo, RegionalInfo, ZonalInfo, SubZonalInfo
from .serializers import (
    CompanyInfoSerializer,
    RegionalInfoSerializer,
    ZonalInfoSerializer,
    SubZonalInfoSerializer,
)


# --- Base ViewSet with shared config ---
class BaseViewSet(viewsets.ModelViewSet):
    """
    Abstract base with advanced filtering, search, and ordering enabled.
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    pagination_class = None  # Optional: add pagination if needed
    search_fields: list[str] = []
    filterset_fields: list[str] = []
    ordering_fields: list[str] = ["id", "name", "created_at"]
    ordering = ["name"]

    def list(self, request, *args, **kwargs):
        """Wrap list responses with { results, count }"""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "results": serializer.data,
            "count": queryset.count()
        })


# --- Company ViewSet ---
class CompanyInfoViewSet(BaseViewSet):
    queryset = CompanyInfo.objects.all()
    serializer_class = CompanyInfoSerializer
    search_fields = ["name", "address", "location", "phone_number"]
    filterset_fields = ["name", "location"]

    @action(detail=True, methods=["get"])
    def regions(self, request, pk=None):
        """Return all regions under a given company"""
        company = self.get_object()
        serializer = RegionalInfoSerializer(company.regions.all(), many=True)
        return Response({
            "results": serializer.data,
            "count": company.regions.count()
        })


# --- Region ViewSet ---
class RegionalInfoViewSet(BaseViewSet):
    queryset = RegionalInfo.objects.select_related("company").all()
    serializer_class = RegionalInfoSerializer
    search_fields = ["name", "address", "office_location", "telephone_number"]
    filterset_fields = ["company", "name"]

    @action(detail=True, methods=["get"])
    def zones(self, request, pk=None):
        """Return all zones under a given region"""
        region = self.get_object()
        serializer = ZonalInfoSerializer(region.zones.all(), many=True)
        return Response({
            "results": serializer.data,
            "count": region.zones.count()
        })


# --- Zone ViewSet ---
class ZonalInfoViewSet(BaseViewSet):
    queryset = ZonalInfo.objects.select_related("region").all()
    serializer_class = ZonalInfoSerializer
    search_fields = ["name", "address"]
    filterset_fields = ["region", "name"]

    @action(detail=True, methods=["get"])
    def sub_zones(self, request, pk=None):
        """Return all sub-zones under a given zone"""
        zone = self.get_object()
        serializer = SubZonalInfoSerializer(zone.sub_zones.all(), many=True)
        return Response({
            "results": serializer.data,
            "count": zone.sub_zones.count()
        })


# --- Sub-Zone ViewSet ---
class SubZonalInfoViewSet(BaseViewSet):
    queryset = SubZonalInfo.objects.select_related("zone").all()
    serializer_class = SubZonalInfoSerializer
    search_fields = ["name", "address"]
    filterset_fields = ["zone", "name"]
