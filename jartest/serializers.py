from rest_framework import serializers
from .models import (
    RawWater, RawWaterAnalysis,
    JarTest, JarResult, JarMeasurement
)
from t.models import TreatmentPlant
from accounts.models import CustomUser
from ca.models import Chemical
from parameters.models import PhysicochemicalParameter


# ============================
# Raw Water Analysis
# ============================
class RawWaterAnalysisCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawWaterAnalysis
        fields = ['parameter', 'value']


class RawWaterAnalysisSerializer(serializers.ModelSerializer):
    parameter_name = serializers.CharField(
        source='parameter.parameter.name',  # parameter -> CoagulatedWaterLimit -> parameter.name
        read_only=True
    )

    class Meta:
        model = RawWaterAnalysis
        fields = '__all__'


# ============================
# Raw Water
# ============================
class RawWaterSerializer(serializers.ModelSerializer):
    treatment_plant_name = serializers.CharField(source='treatment_plant.name', read_only=True)
    analyses = RawWaterAnalysisSerializer(many=True, read_only=True)
    analysis_inputs = RawWaterAnalysisCreateSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = RawWater
        fields = '__all__'

    def create(self, validated_data):
        analysis_inputs = validated_data.pop('analysis_inputs', [])
        raw_water = RawWater.objects.create(**validated_data)
        for a in analysis_inputs:
            RawWaterAnalysis.objects.create(raw_water=raw_water, **a)
        return raw_water

    def update(self, instance, validated_data):
        analysis_inputs = validated_data.pop('analysis_inputs', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if analysis_inputs is not None:
            instance.analyses.all().delete()
            for a in analysis_inputs:
                RawWaterAnalysis.objects.create(raw_water=instance, **a)
        return instance


# ============================
# Jar Measurement
# ============================
class JarMeasurementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = JarMeasurement
        fields = ['parameter', 'value']


class JarMeasurementSerializer(serializers.ModelSerializer):
    parameter_name = serializers.CharField(
        source='parameter.parameter.name',  # parameter -> CoagulatedWaterLimit -> parameter.name
        read_only=True
    )

    class Meta:
        model = JarMeasurement
        fields = '__all__'


# ============================
# Jar Result
# ============================
class JarResultCreateSerializer(serializers.ModelSerializer):
    measurements = JarMeasurementCreateSerializer(many=True, write_only=True)

    class Meta:
        model = JarResult
        fields = ['jar_number', 'dosage_mg_per_l', 'floc_observation_time', 'measurements']

    def create(self, validated_data):
        measurements = validated_data.pop('measurements', [])
        jar_result = JarResult.objects.create(**validated_data)
        for m in measurements:
            JarMeasurement.objects.create(jar_result=jar_result, **m)
        return jar_result


class JarResultSerializer(serializers.ModelSerializer):
    measurements = JarMeasurementSerializer(many=True, read_only=True)

    class Meta:
        model = JarResult
        fields = '__all__'


# ============================
# Jar Test
# ============================
class JarTestSerializer(serializers.ModelSerializer):
    treatment_plant_name = serializers.CharField(source='treatment_plant.name', read_only=True)
    analyst_name = serializers.CharField(source='analyst.get_full_name', read_only=True)
    jar_results = JarResultSerializer(many=True, read_only=True)
    verified_by_name = serializers.CharField(source='verified_by.get_full_name', read_only=True)
    confirmed_by_name = serializers.CharField(source='confirmed_by.get_full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)

    class Meta:
        model = JarTest
        fields = '__all__'


class JarTestCreateSerializer(serializers.ModelSerializer):
    jar_result_inputs = JarResultCreateSerializer(many=True, write_only=True)

    class Meta:
        model = JarTest
        fields = [
            'treatment_plant', 'raw_water', 'test_date', 'coagulant', 'remarks', 'analyst', 'jar_result_inputs'
        ]

    def create(self, validated_data):
        jar_result_inputs = validated_data.pop('jar_result_inputs', [])
        jar_test = JarTest.objects.create(**validated_data)
        for jr in jar_result_inputs:
            measurements = jr.pop('measurements', [])
            jar_result = JarResult.objects.create(jar_test=jar_test, **jr)
            for m in measurements:
                JarMeasurement.objects.create(jar_result=jar_result, **m)
        jar_test.rank_jar_results()
        return jar_test
