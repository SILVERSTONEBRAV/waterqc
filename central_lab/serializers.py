from rest_framework import serializers
from .models import (
    SampleCategory,
    KabeteSamplingPoint, GigiriSamplingPoint,
    RegionSample, FCASample, CatchmentSample, KabeteSample, GigiriSample,
    RegionSampleAnalysis, FCASampleAnalysis, CatchmentSampleAnalysis, KabeteSampleAnalysis, GigiriSampleAnalysis,
    RegionSampleParameterResult, FCASampleParameterResult, CatchmentSampleParameterResult, KabeteSampleParameterResult, GigiriSampleParameterResult
)

# --- Sample Category Serializer ---
class SampleCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SampleCategory
        fields = ['id', 'name', 'description', 'is_active']

# --- Sampling Point Serializers ---
class KabeteSamplingPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = KabeteSamplingPoint
        fields = ['id', 'name', 'description', 'gps_coordinates', 'last_sampled_date', 'total_times_sampled']

class GigiriSamplingPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = GigiriSamplingPoint
        fields = ['id', 'name', 'description', 'gps_coordinates', 'last_sampled_date', 'total_times_sampled']

# --- Parameter Result Base Serializer ---
class ParameterResultBaseSerializer(serializers.ModelSerializer):
    parameter_name = serializers.CharField(source='parameter.name', read_only=True)
    min_standard = serializers.DecimalField(source='parameter.min_standard', max_digits=10, decimal_places=2, read_only=True)
    max_standard = serializers.DecimalField(source='parameter.max_standard', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        abstract = True

# --- Parameter Result Serializers ---
class RegionSampleParameterResultSerializer(ParameterResultBaseSerializer):
    class Meta:
        model = RegionSampleParameterResult
        fields = '__all__'

class FCASampleParameterResultSerializer(ParameterResultBaseSerializer):
    class Meta:
        model = FCASampleParameterResult
        fields = '__all__'

class CatchmentSampleParameterResultSerializer(ParameterResultBaseSerializer):
    class Meta:
        model = CatchmentSampleParameterResult
        fields = '__all__'

class KabeteSampleParameterResultSerializer(ParameterResultBaseSerializer):
    class Meta:
        model = KabeteSampleParameterResult
        fields = '__all__'

class GigiriSampleParameterResultSerializer(ParameterResultBaseSerializer):
    class Meta:
        model = GigiriSampleParameterResult
        fields = '__all__'

# --- Analysis Serializers ---
class RegionSampleAnalysisSerializer(serializers.ModelSerializer):
    parameter_results = RegionSampleParameterResultSerializer(many=True, read_only=True)

    class Meta:
        model = RegionSampleAnalysis
        fields = '__all__'

class FCASampleAnalysisSerializer(serializers.ModelSerializer):
    parameter_results = FCASampleParameterResultSerializer(many=True, read_only=True)

    class Meta:
        model = FCASampleAnalysis
        fields = '__all__'

class CatchmentSampleAnalysisSerializer(serializers.ModelSerializer):
    parameter_results = CatchmentSampleParameterResultSerializer(many=True, read_only=True)

    class Meta:
        model = CatchmentSampleAnalysis
        fields = '__all__'

class KabeteSampleAnalysisSerializer(serializers.ModelSerializer):
    parameter_results = KabeteSampleParameterResultSerializer(many=True, read_only=True)

    class Meta:
        model = KabeteSampleAnalysis
        fields = '__all__'

class GigiriSampleAnalysisSerializer(serializers.ModelSerializer):
    parameter_results = GigiriSampleParameterResultSerializer(many=True, read_only=True)

    class Meta:
        model = GigiriSampleAnalysis
        fields = '__all__'

# --- Sample Serializers ---
class RegionSampleSerializer(serializers.ModelSerializer):
    sampling_point = serializers.StringRelatedField()
    category = SampleCategorySerializer(read_only=True)
    analysis = RegionSampleAnalysisSerializer(read_only=True)

    class Meta:
        model = RegionSample
        fields = '__all__'

class FCASampleSerializer(serializers.ModelSerializer):
    sampling_point = serializers.StringRelatedField()
    analysis = FCASampleAnalysisSerializer(read_only=True)

    class Meta:
        model = FCASample
        fields = '__all__'

class CatchmentSampleSerializer(serializers.ModelSerializer):
    sampling_point = serializers.StringRelatedField()
    analysis = CatchmentSampleAnalysisSerializer(read_only=True)

    class Meta:
        model = CatchmentSample
        fields = '__all__'

class KabeteSampleSerializer(serializers.ModelSerializer):
    sampling_point = KabeteSamplingPointSerializer(read_only=True)
    analysis = KabeteSampleAnalysisSerializer(read_only=True)

    class Meta:
        model = KabeteSample
        fields = '__all__'

class GigiriSampleSerializer(serializers.ModelSerializer):
    sampling_point = GigiriSamplingPointSerializer(read_only=True)
    analysis = GigiriSampleAnalysisSerializer(read_only=True)

    class Meta:
        model = GigiriSample
        fields = '__all__'
