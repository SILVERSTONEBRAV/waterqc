from django.urls import path
from core.views import NAMUBUYA, fields_schema,  registry_router
from t.DashboardView import DashboardView

app_name = "reports"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),

    # collection
    path("<str:model>/<str:action>/", NAMUBUYA.as_view(), name="registry-list"),

    # object
    path("<str:model>/<str:pk>/<str:action>/", NAMUBUYA.as_view(), name="registry-object"),
    path("<str:app_label>/<str:model_name>/schema/", fields_schema),
    path("<str:app_label>/<str:model>/<str:action>/", registry_router),



]
