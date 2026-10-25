from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import (
    HeavyMetalAnalysis,
    HeavyMetalParameter,
    HeavyMetalAnalysisState,
)
from t.models import HeavyMetalLimit
from accounts.serializers import CustomUserSerializer  # Import the correct User Serializer


class HeavyMetalLimitSerializer(serializers.ModelSerializer):
    parameter_name = serializers.CharField(source='parameter.name', read_only=True)

    class Meta:
        model = HeavyMetalLimit
        fields = ['id', 'parameter_name', 'parameter', 'limit']


class HeavyMetalParameterSerializer(serializers.ModelSerializer):
    parameter_name = serializers.CharField(source='parameter.parameter.name', read_only=True)
    result_value = serializers.FloatField(source='value')
    entry_status = serializers.CharField(read_only=True)

    class Meta:
        model = HeavyMetalParameter
        fields = ['id', 'parameter', 'parameter_name', 'result_value', 'entry_status']

    def create(self, validated_data):
        validated_data['entry_status'] = HeavyMetalParameter.EntryStatus.RECORDED
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'value' in validated_data:
            instance.entry_status = HeavyMetalParameter.EntryStatus.RECORDED
        return super().update(instance, validated_data)


class HeavyMetalAnalysisListSerializer(serializers.ModelSerializer):
    treatment_plant_name = serializers.CharField(source='treatment_plant.name', read_only=True)
    phase_name = serializers.CharField(source='treatment_plant_phase.name', read_only=True)
    created_by = CustomUserSerializer(read_only=True)
    analysed_by = CustomUserSerializer(read_only=True)
    verified_by = CustomUserSerializer(read_only=True)
    confirmed_by = CustomUserSerializer(read_only=True)
    approved_by = CustomUserSerializer(read_only=True)

    class Meta:
        model = HeavyMetalAnalysis
        fields = [
            'id', 'uuid', 'sampling_date', 'treatment_plant', 'treatment_plant_name',
            'treatment_plant_phase', 'phase_name', 'sample_source', 'state',
            'created_by', 'analysed_by', 'verified_by', 'confirmed_by', 'approved_by',
            'remarks', 'created_at', 'updated_at',
        ]


class HeavyMetalAnalysisDetailSerializer(serializers.ModelSerializer):
    parameters = HeavyMetalParameterSerializer(many=True, read_only=True)
    created_by = CustomUserSerializer(read_only=True)
    analysed_by = CustomUserSerializer(read_only=True)
    verified_by = CustomUserSerializer(read_only=True)
    confirmed_by = CustomUserSerializer(read_only=True)
    approved_by = CustomUserSerializer(read_only=True)

    class Meta:
        model = HeavyMetalAnalysis
        fields = [
            'id', 'uuid', 'sampling_date', 'treatment_plant', 'treatment_plant_phase',
            'sample_source', 'state', 'remarks',
            'created_by', 'analysed_by', 'verified_by', 'confirmed_by', 'approved_by',
            'parameters', 'created_at', 'updated_at'
        ]


class HeavyMetalAnalysisCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeavyMetalAnalysis
        fields = [
            'sampling_date', 'treatment_plant', 'treatment_plant_phase',
            'sample_source', 'remarks'
        ]

    def validate(self, data):
        instance = HeavyMetalAnalysis(**data)
        instance.clean()  # trigger model validations
        return data

    def create(self, validated_data):
        request = self.context['request']
        validated_data['created_by'] = request.user
        return super().create(validated_data)


class HeavyMetalAnalysisTransitionSerializer(serializers.Serializer):
    new_state = serializers.ChoiceField(choices=HeavyMetalAnalysisState.choices)

    def validate_new_state(self, value):
        analysis = self.context['analysis']
        current_state = analysis.state
        allowed = dict(HeavyMetalAnalysisState.choices).get(value)
        if value not in dict(HeavyMetalAnalysisState.choices):
            raise serializers.ValidationError(_(f"Invalid state '{value}'"))
        if value not in analysis.get_next_states():
            raise serializers.ValidationError(_(f"Transition from '{current_state}' to '{value}' is not allowed."))
        return value

    def save(self):
        user = self.context['request'].user
        analysis = self.context['analysis']
        new_state = self.validated_data['new_state']
        analysis.transition_state(new_state, user)
        return analysis
