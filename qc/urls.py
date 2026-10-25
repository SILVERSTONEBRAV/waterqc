from django.urls import path
from .ViewDashboard import DashboardView
from core.views import (NAMUBUYA, fields_schema, registry_router,)
from .views import AnalysisWorksheetSaveView, AnalysisWorksheetView
from .views.result_card import (ResultCardEntryView,)
from .views.filter_readings import FilterReadingsUpdateView
from .views.noncompliance import QCNonComplianceDashboardView
from .views.reports import QCInsightsDashboardView, QCReportsView, QCVisualizationDashboardView
from .views.scada import SCADADashboardView


app_name = "qc"

urlpatterns = [
    # Registry / command dashboard
    path("", DashboardView.as_view(), name="dashboard"),
    # QCA analytical matrix (result cards)
    path("quality_control/", ResultCardEntryView.as_view(), name="quality_control"),
    path("quality_control/reports/", QCReportsView.as_view(), name="reports"),
    path("quality_control/analytics/", QCInsightsDashboardView.as_view(), name="analytics"),
    path("quality_control/visualizations/", QCVisualizationDashboardView.as_view(), name="visualizations"),
    path("quality_control/non-compliance/", QCNonComplianceDashboardView.as_view(), name="noncompliance"),
    path("quality_control/filters/update/", FilterReadingsUpdateView.as_view(), name="filter_readings_update"),
    # SCADA Quality Control & Sensor Telemetry Command Center
    path("scada/", SCADADashboardView.as_view(), name="scada_dashboard"),
    # Back-compat aliases (older templates / bookmarks)
    path("worksheet/", AnalysisWorksheetView.as_view(), name="analysis-worksheet"),
    path("worksheet/save/", AnalysisWorksheetSaveView.as_view(), name="analysis-worksheet-save"),
    path("cards/", ResultCardEntryView.as_view(), name="result-cards"),
    path("quality_control", ResultCardEntryView.as_view(), name="quality_control_noslash"),
    path("matrix/", ResultCardEntryView.as_view(), name="dashboard1"),

    path("<str:model>/<str:action>/", NAMUBUYA.as_view(), name="registry-list"),
    path("<str:model>/<str:pk>/<str:action>/", NAMUBUYA.as_view(), name="registry-object"),
    path("<str:app_label>/<str:model_name>/schema/", fields_schema, name="fields_schema"),
    path("<str:app_label>/<str:model>/<str:action>/", registry_router, name="registry_router"),
    path(
        "<str:app_label>/<str:model>/<str:pk>/<str:action>/",
        registry_router,
        name="registry_router_object",
    ),
]

