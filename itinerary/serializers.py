from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import (
    SamplingPlan, DynamicSamplingPoint, Itinerary, SampleCategory,
    RegionSamplingPoint, FCARegionSamplingPoint, CatchmentSamplingPoint
)

# --- Polymorphic Sampling Point Serializers ---
class RegionSamplingPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegionSamplingPoint
        fields = '__all__'

class FCARegionSamplingPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCARegionSamplingPoint
        fields = '__all__'

class CatchmentSamplingPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatchmentSamplingPoint
        fields = '__all__'

# --- Sampling Point Type Serializer Registry ---
SAMPLING_POINT_SERIALIZER_REGISTRY = {
    'region': RegionSamplingPointSerializer,
    'fca': FCARegionSamplingPointSerializer,
    'catchment': CatchmentSamplingPointSerializer
}

# --- Dynamic Sampling Point Serializer ---
class DynamicSamplingPointSerializer(serializers.ModelSerializer):
    point = serializers.SerializerMethodField()

    class Meta:
        model = DynamicSamplingPoint
        fields = ['id', 'content_type', 'object_id', 'point']

    def get_point(self, obj):
        model_name = obj.content_type.model
        serializer_class = SAMPLING_POINT_SERIALIZER_REGISTRY.get(model_name)
        if not serializer_class:
            return None
        return serializer_class(obj.point, context=self.context).data

# --- Sample Category Serializer ---
class SampleCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SampleCategory
        fields = '__all__'

# --- Sampling Plan Serializer ---
class SamplingPlanSerializer(serializers.ModelSerializer):
    coverage_percentage = serializers.ReadOnlyField()

    class Meta:
        model = SamplingPlan
        fields = '__all__'

# --- Writable Nested Sampling Point Field ---
class DynamicSamplingPointWritableField(serializers.PrimaryKeyRelatedField):
    def to_representation(self, value):
        return DynamicSamplingPointSerializer(value, context=self.context).data

# --- Itinerary Serializer (Nested, Writable, Advanced) ---
class ItinerarySerializer(serializers.ModelSerializer):
    sampling_points = DynamicSamplingPointWritableField(
        many=True, queryset=DynamicSamplingPoint.objects.all()
    )
    itinerary_type = serializers.SerializerMethodField()
    remaining_slots = serializers.ReadOnlyField()
    is_full = serializers.ReadOnlyField()

    class Meta:
        model = Itinerary
        fields = [
            'id', 'name', 'sampling_date', 'max_sampling_points', 'status', 'is_locked',
            'assignment_strategy', 'remarks', 'content_type', 'object_id',
            'itinerary_type', 'sampling_points', 'remaining_slots', 'is_full'
        ]

    def get_itinerary_type(self, obj):
        return str(obj.itinerary_type)

    def validate(self, data):
        if data.get('sampling_points') and len(data['sampling_points']) > data.get('max_sampling_points', obj.max_sampling_points):
            raise serializers.ValidationError(f"Cannot assign more than {data['max_sampling_points']} sampling points.")
        return data

    def create(self, validated_data):
        sampling_points = validated_data.pop('sampling_points', [])
        itinerary = super().create(validated_data)
        itinerary.sampling_points.set(sampling_points)
        return itinerary

    def update(self, instance, validated_data):
        sampling_points = validated_data.pop('sampling_points', None)
        instance = super().update(instance, validated_data)
        if sampling_points is not None:
            instance.sampling_points.set(sampling_points)
        return instance
