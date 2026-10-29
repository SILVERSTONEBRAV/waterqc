from django.urls import path
from .ViewDashboard import DashboardView, FilterDetailView
from core.views import (NAMUBUYA,fields_schema,registry_router,)

app_name = "filtered_water"

urlpatterns = [
    # ---------------- Dashboard ----------------
    path("", DashboardView.as_view(), name="dashboard"),
    path("filters/<int:filter_id>/", FilterDetailView.as_view(), name="filter_detail"),
    path( "<str:model>/<str:action>/", NAMUBUYA.as_view(),name="registry-list",),
    path( "<str:model>/<str:pk>/<str:action>/",NAMUBUYA.as_view(),name="registry-object",),
    path( "<str:app_label>/<str:model_name>/schema/",fields_schema,name="fields_schema", ),
    path( "<str:app_label>/<str:model>/<str:action>/",registry_router,name="registry_router",),
    path( "<str:app_label>/<str:model>/<str:pk>/<str:action>/", registry_router,name="registry_router_object", ),
]
