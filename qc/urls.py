from django.urls import path
from .ViewDashboard import DashboardView
from core.views import (NAMUBUYA,fields_schema,registry_router,)
from .views import (AnalysisWorksheetView, AnalysisWorksheetSaveView)
from .views.result_card import (ResultCardEntryView,)

app_name = "qc"

urlpatterns = [
    # ---------------- Dashboard ----------------
    path("", DashboardView.as_view(), name="dashboard"),

    # ---------------- Worksheets & Result Cards ----------------
    path("worksheet/", AnalysisWorksheetView.as_view(), name="analysis-worksheet"),
    path("worksheet/save/", AnalysisWorksheetSaveView.as_view(), name="analysis-worksheet-save"),
    path("cards/", ResultCardEntryView.as_view(), name="result-cards"),

    path( "<str:model>/<str:action>/", NAMUBUYA.as_view(),name="registry-list",),
    path( "<str:model>/<str:pk>/<str:action>/",NAMUBUYA.as_view(),name="registry-object",),
    path( "<str:app_label>/<str:model_name>/schema/",fields_schema,name="fields_schema", ),
    path( "<str:app_label>/<str:model>/<str:action>/",registry_router,name="registry_router",),
    path( "<str:app_label>/<str:model>/<str:pk>/<str:action>/", registry_router,name="registry_router_object", ),

]

