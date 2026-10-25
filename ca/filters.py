#filters.py
from django_filters import rest_framework as filters
from .models import ChemicalBatch, ChemicalAnalysisRequest


class ChemicalBatchFilter(filters.FilterSet):
    min_received_date = filters.DateFilter(field_name="received_date", lookup_expr='gte')
    max_received_date = filters.DateFilter(field_name="received_date", lookup_expr='lte')
    chemical = filters.NumberFilter(field_name="chemical_id")
    treatment_plant = filters.NumberFilter(field_name="treatment_plant_id")
    status = filters.CharFilter(field_name="status", lookup_expr='iexact')
    location = filters.NumberFilter(field_name="location_id")

    class Meta:
        model = ChemicalBatch
        fields = ['chemical', 'status', 'treatment_plant', 'location']


class ChemicalAnalysisRequestFilter(filters.FilterSet):
    min_delivery_date = filters.DateFilter(field_name="delivery_date", lookup_expr='gte')
    max_delivery_date = filters.DateFilter(field_name="delivery_date", lookup_expr='lte')
    chemical = filters.NumberFilter(field_name="batch__chemical_id")
    treatment_plant = filters.NumberFilter(field_name="batch__treatment_plant_id")
    status = filters.CharFilter(field_name="status", lookup_expr='iexact')
    location = filters.NumberFilter(field_name="batch__location_id")

    class Meta:
        model = ChemicalAnalysisRequest
        fields = ['chemical', 'status', 'treatment_plant', 'delivery_date', 'location']
