from django.urls import path
from core.workflow_view import WorkflowDashboardView

app_name = "core"

urlpatterns = [
    path("workflow/", WorkflowDashboardView.as_view(), name="workflow-dashboard"),
]


