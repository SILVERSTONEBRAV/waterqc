from rest_framework import serializers
from .models import SampleType, AnalysisSchedule

class SampleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SampleType
        fields = '__all__'

class AnalysisScheduleSerializer(serializers.ModelSerializer):
    sample_type = SampleTypeSerializer()

    class Meta:
        model = AnalysisSchedule
        fields = '__all__'
