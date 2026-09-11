from rest_framework import viewsets
from .models import SampleType, AnalysisSchedule
from .serializers import SampleTypeSerializer, AnalysisScheduleSerializer

class SampleTypeViewSet(viewsets.ModelViewSet):
    queryset = SampleType.objects.all()
    serializer_class = SampleTypeSerializer

class AnalysisScheduleViewSet(viewsets.ModelViewSet):
    queryset = AnalysisSchedule.objects.all()
    serializer_class = AnalysisScheduleSerializer
