from rest_framework import serializers
from django.core.exceptions import ValidationError
from accounts.models import CustomUser
from .models import (
    MicrobialAnalysis,
    MicrobialMethod,
    MicrobialParameterResult,
    TreatedWaterParameterResult,
    MicrobialAnalysisState,

)
from t.models import TreatmentPlant, TreatmentPlantPhase, TreatedWaterLimit, MicrobialLimit


# User Serializer (Minimal Info)
class UserBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'first_name', 'last_name', 'email']


# Microbial Method Serializer
class MicrobialMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = MicrobialMethod
        fields = ['id', 'name', 'description', 'incubation_time', 'confirmatory_tests']


# Microbial Parameter Result Serializer
class MicrobialParameterResultSerializer(serializers.ModelSerializer):
    parameter_name = serializers.CharField(source='parameter.parameter.name', read_only=True)

    class Meta:
        model = MicrobialParameterResult
        fields = ['id', 'parameter', 'parameter_name', 'result_value', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


# Treated Water Parameter Result Serializer
class TreatedWaterParameterResultSerializer(serializers.ModelSerializer):
    parameter_name = serializers.CharField(source='parameter.parameter.name', read_only=True)

    class Meta:
        model = TreatedWaterParameterResult
        fields = ['id', 'parameter', 'parameter_name', 'result_value', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


# Microbial Analysis Serializer
class MicrobialAnalysisSerializer(serializers.ModelSerializer):
    method = MicrobialMethodSerializer(read_only=True)
    method_id = serializers.PrimaryKeyRelatedField(source='method', queryset=MicrobialMethod.objects.all(), write_only=True)

    treatment_plant_name = serializers.CharField(source='treatment_plant.name', read_only=True)
    treatment_plant_phase_name = serializers.CharField(source='treatment_plant_phase.name', read_only=True)

    treatment_plant = serializers.PrimaryKeyRelatedField(queryset=TreatmentPlant.objects.all())
    treatment_plant_phase = serializers.PrimaryKeyRelatedField(queryset=TreatmentPlantPhase.objects.all())

    created_by = UserBasicSerializer(read_only=True)
    analysed_by = UserBasicSerializer(read_only=True)
    verified_by = UserBasicSerializer(read_only=True)
    confirmed_by = UserBasicSerializer(read_only=True)
    approved_by = UserBasicSerializer(read_only=True)

    microbial_parameters = MicrobialParameterResultSerializer(many=True, read_only=True)
    treated_parameters = TreatedWaterParameterResultSerializer(many=True, read_only=True)

    class Meta:
        model = MicrobialAnalysis
        fields = [
            'id', 'uuid', 'sampling_date', 'state',
            'method', 'method_id',
            'treatment_plant', 'treatment_plant_name',
            'treatment_plant_phase', 'treatment_plant_phase_name',
            'incubation_start', 'incubation_end',
            'created_by', 'analysed_by', 'verified_by', 'confirmed_by', 'approved_by',
            'microbial_parameters', 'treated_parameters',
            'treated_water_analysis', 'remarks',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'incubation_start', 'incubation_end', 'created_at', 'updated_at']


# Serializer to handle state transitions
class MicrobialAnalysisStateTransitionSerializer(serializers.Serializer):
    new_state = serializers.ChoiceField(choices=MicrobialAnalysisState.choices)

    def validate(self, data):
        analysis: MicrobialAnalysis = self.context['analysis']
        user = self.context['request'].user
        new_state = data['new_state']

        try:
            analysis.transition_state(new_state, user)
        except ValidationError as e:
            raise serializers.ValidationError(str(e))
        return data
