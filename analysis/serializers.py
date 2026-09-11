# analysis/serializers.py
from rest_framework import serializers
from .models import AnalysisData, StatisticalTestResult, ClusteringResult, RegressionResult

class AnalysisDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisData
        fields = '__all__'

class StatisticalTestResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatisticalTestResult
        fields = '__all__'

class ClusteringResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClusteringResult
        fields = '__all__'

class RegressionResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegressionResult
        fields = '__all__'
