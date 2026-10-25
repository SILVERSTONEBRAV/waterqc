# monitoring/urls.py
from django.urls import path
from . import views

app_name = "monitoring"

urlpatterns = [
    path("", views.MonitoringDashboardView.as_view(), name="dashboard"),
    # JSON API endpoints consumed by the frontend
    path("api/system/", views.SystemMetricsAPI.as_view(), name="api_system"),
    path("api/realtime/", views.RealtimeTelemetryAPI.as_view(), name="api_realtime"),
    path("api/docker/containers/", views.DockerContainersAPI.as_view(), name="api_docker_containers"),
    path("api/docker/action/", views.DockerActionAPI.as_view(), name="api_docker_action"),
    path("api/docker/logs/", views.DockerLogsAPI.as_view(), name="api_docker_logs"),
    path("api/docker/compose/", views.DockerComposeAPI.as_view(), name="api_docker_compose"),
    path("api/k8s/", views.KubernetesAPI.as_view(), name="api_k8s"),
    path("api/security/", views.SecurityAuditAPI.as_view(), name="api_security"),
    path("api/health/", views.AppHealthAPI.as_view(), name="api_health"),
    path("api/report/daily/", views.DailyReportAPI.as_view(), name="api_daily_report"),
]
