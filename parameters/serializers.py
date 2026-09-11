from rest_framework import serializers
from .models import (
    PhysicochemicalParameter, MicrobialParameter, HeavyMetalParameter,
    WWQParameter_qad, CWQParameter_qad, DistributionParameter_qad,
    GigiriParameter_qad, KabeteParameter_qad, CatchmentParameter_qad,
    ParameterUnit, ParameterTypeRegistry
)
from django.core.exceptions import ValidationError

# --- Base Parameter Serializer ---
class BaseParameterSerializer(serializers.ModelSerializer):
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)

    class Meta:
        model = None  # To be dynamically assigned
        fields = ['id', 'uuid', 'name', 'unit', 'unit_display', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'uuid', 'created_at', 'updated_at']

# --- Standardized Parameter Mixin Serializer ---
class StandardizedFieldsMixin(serializers.ModelSerializer):
    def validate(self, data):
        min_standard = data.get('min_standard', getattr(self.instance, 'min_standard', None))
        max_standard = data.get('max_standard', getattr(self.instance, 'max_standard', None))
        if min_standard is not None and max_standard is not None:
            if min_standard >= max_standard:
                raise serializers.ValidationError("Minimum standard must be less than maximum standard.")
        return data

    class Meta:
        fields = ['min_standard', 'max_standard']

# --- Concrete Parameter Serializers ---
class PhysicochemicalParameterSerializer(BaseParameterSerializer):
    class Meta(BaseParameterSerializer.Meta):
        model = PhysicochemicalParameter

class MicrobialParameterSerializer(BaseParameterSerializer):
    class Meta(BaseParameterSerializer.Meta):
        model = MicrobialParameter

class HeavyMetalParameterSerializer(BaseParameterSerializer):
    class Meta(BaseParameterSerializer.Meta):
        model = HeavyMetalParameter

class CatchmentParameterSerializer(BaseParameterSerializer):
    class Meta(BaseParameterSerializer.Meta):
        model = CatchmentParameter_qad

# --- Standardized Parameter Serializers ---
class WWQParameterSerializer(StandardizedFieldsMixin, BaseParameterSerializer):
    class Meta(BaseParameterSerializer.Meta):
        model = WWQParameter_qad
        fields = BaseParameterSerializer.Meta.fields + StandardizedFieldsMixin.Meta.fields

class CWQParameterSerializer(StandardizedFieldsMixin, BaseParameterSerializer):
    class Meta(BaseParameterSerializer.Meta):
        model = CWQParameter_qad
        fields = BaseParameterSerializer.Meta.fields + StandardizedFieldsMixin.Meta.fields

class DistributionParameterSerializer(StandardizedFieldsMixin, BaseParameterSerializer):
    class Meta(BaseParameterSerializer.Meta):
        model = DistributionParameter_qad
        fields = BaseParameterSerializer.Meta.fields + StandardizedFieldsMixin.Meta.fields

class GigiriParameterSerializer(StandardizedFieldsMixin, BaseParameterSerializer):
    class Meta(BaseParameterSerializer.Meta):
        model = GigiriParameter_qad
        fields = BaseParameterSerializer.Meta.fields + StandardizedFieldsMixin.Meta.fields

class KabeteParameterSerializer(StandardizedFieldsMixin, BaseParameterSerializer):
    class Meta(BaseParameterSerializer.Meta):
        model = KabeteParameter_qad
        fields = BaseParameterSerializer.Meta.fields + StandardizedFieldsMixin.Meta.fields

class MicrobialParameterStandardizedSerializer(StandardizedFieldsMixin, BaseParameterSerializer):
    class Meta(BaseParameterSerializer.Meta):
        model = ParameterTypeRegistry.get('Microbial')
        fields = BaseParameterSerializer.Meta.fields + StandardizedFieldsMixin.Meta.fields

# --- Parameter Unit Serializer ---
class ParameterUnitSerializer(serializers.Serializer):
    code = serializers.CharField()
    description = serializers.CharField()

# --- Dynamic Registry Exposure Serializer ---
class ParameterRegistrySerializer(serializers.Serializer):
    key = serializers.CharField()
    class_name = serializers.CharField(source='__name__')
