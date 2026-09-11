# reports/serializers.py
from rest_framework import serializers
from .models import DailyReport, WeeklyReport, MonthlyReport, AnnualReport, CustomDateRangeReport

class DailyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReport
        fields = '__all__'

class WeeklyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeeklyReport
        fields = '__all__'

class MonthlyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyReport
        fields = '__all__'

class AnnualReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnualReport
        fields = '__all__'

class CustomDateRangeReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomDateRangeReport
        fields = '__all__'
