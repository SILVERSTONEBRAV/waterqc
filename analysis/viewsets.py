# analysis/viewsets.py
from rest_framework import viewsets
from .models import AnalysisData, StatisticalTestResult, ClusteringResult, RegressionResult
from .serializers import AnalysisDataSerializer, StatisticalTestResultSerializer, ClusteringResultSerializer, RegressionResultSerializer

class AnalysisDataViewSet(viewsets.ModelViewSet):
    queryset = AnalysisData.objects.all()
    serializer_class = AnalysisDataSerializer

class StatisticalTestResultViewSet(viewsets.ModelViewSet):
    queryset = StatisticalTestResult.objects.all()
    serializer_class = StatisticalTestResultSerializer

class ClusteringResultViewSet(viewsets.ModelViewSet):
    queryset = ClusteringResult.objects.all()
    serializer_class = ClusteringResultSerializer

class RegressionResultViewSet(viewsets.ModelViewSet):
    queryset = RegressionResult.objects.all()
    serializer_class = RegressionResultSerializer
