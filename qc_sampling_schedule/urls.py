from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .viewsets import SampleTypeViewSet, AnalysisScheduleViewSet

router = DefaultRouter()
router.register(r'sample-types', SampleTypeViewSet)
router.register(r'schedules', AnalysisScheduleViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
]
