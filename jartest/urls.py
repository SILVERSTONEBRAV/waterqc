from django.urls import path
from .views_dashboard import DosagePredictionView, JarTestDashboardView
from .ViewDashboard import DashboardView
from core.views import (NAMUBUYA, fields_schema, registry_router)

app_name = "jartest"

urlpatterns = [
    # ---------------- Advanced Analytical Dashboard ----------------
    path("", JarTestDashboardView.as_view(), name="dashboard"),
    path("cards/", JarTestDashboardView.as_view(), name="cards"),
    path("predict-dosage/", DosagePredictionView.as_view(), name="predict_dosage"),
    path("registry-overview/", DashboardView.as_view(), name="registry-dashboard"),
    path("<str:model>/<str:action>/", NAMUBUYA.as_view(), name="registry-list"),
    path("<str:model>/<str:pk>/<str:action>/", NAMUBUYA.as_view(), name="registry-object"),
    path("<str:app_label>/<str:model_name>/schema/", fields_schema, name="fields_schema"),
    path("<str:app_label>/<str:model>/<str:action>/", registry_router, name="registry_router"),
    path("<str:app_label>/<str:model>/<str:pk>/<str:action>/", registry_router, name="registry_router_object"),

]
