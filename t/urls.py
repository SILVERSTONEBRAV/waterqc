# t/urls.py

from django.urls import path

from core.views import (
    NAMUBUYA,
    fields_schema,
    registry_router,
)
from t.DashboardView import DashboardView

app_name = "t"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard", ),
    path("treatmentplant/create/", NAMUBUYA.as_view(), {"model": "treatmentplant", "action": "create"}, name="treatmentplant_create"),
    path("treatmentplant/<str:pk>/edit/", NAMUBUYA.as_view(), {"model": "treatmentplant", "action": "update"}, name="treatmentplant_update"),
    path("treatmentplant/<str:pk>/delete/", NAMUBUYA.as_view(), {"model": "treatmentplant", "action": "delete"}, name="treatmentplant_delete"),
    path("<str:model>/<str:action>/", NAMUBUYA.as_view(), name="registry-list",),
    path("<str:model>/<str:pk>/<str:action>/", NAMUBUYA.as_view(), name="registry-object",),
    path("<str:app_label>/<str:model_name>/schema/",fields_schema,name="fields_schema", ),
    path("<str:app_label>/<str:model>/<str:action>/", registry_router,name="registry_router",),
    path("<str:app_label>/<str:model>/<str:pk>/<str:action>/", registry_router, name="registry_router_object",),
]