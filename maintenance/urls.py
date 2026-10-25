from django.urls import path

from core.views import NAMUBUYA, fields_schema, registry_router

from .ViewDashboard import DashboardView
from . import views

app_name = "maintenance"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("dashboard/", DashboardView.as_view(), name="dashboard-view"),
    path("actions/incident/report/", views.report_incident, name="report_incident"),
    # Workflow actions
    path(
        "actions/request/<uuid:pk>/approve/",
        views.approve_request,
        name="approve_request",
    ),
    path(
        "actions/request/<uuid:pk>/convert/",
        views.convert_request,
        name="convert_request",
    ),
    path(
        "actions/order/<uuid:pk>/assign/",
        views.assign_order,
        name="assign_order",
    ),
    path(
        "actions/order/<uuid:pk>/start/",
        views.start_order,
        name="start_order",
    ),
    path(
        "actions/order/<uuid:pk>/complete/",
        views.complete_order,
        name="complete_order",
    ),
    path(
        "actions/incident/<uuid:pk>/acknowledge/",
        views.acknowledge_incident,
        name="acknowledge_incident",
    ),
    path(
        "actions/incident/<uuid:pk>/escalate/",
        views.escalate_incident,
        name="escalate_incident",
    ),
    path(
        "actions/incident/<uuid:pk>/assign/",
        views.assign_incident,
        name="assign_incident",
    ),
    path(
        "actions/incident/<uuid:pk>/resolve/",
        views.resolve_incident,
        name="resolve_incident",
    ),
    path(
        "actions/incident/<uuid:pk>/close/",
        views.close_incident,
        name="close_incident",
    ),
    path(
        "actions/incident/<uuid:pk>/reopen/",
        views.reopen_incident,
        name="reopen_incident",
    ),
    path(
        "actions/house/<uuid:pk>/maintenance/",
        views.mark_house_maintenance,
        name="mark_house_maintenance",
    ),
    path(
        "actions/house/<uuid:pk>/activate/",
        views.activate_house,
        name="activate_house",
    ),
    path(
        "actions/housing/check-in/",
        views.check_in_occupant,
        name="check_in_occupant",
    ),
    path(
        "actions/housing/<uuid:pk>/check-out/",
        views.check_out_occupant,
        name="check_out_occupant",
    ),
    path(
        "actions/housing/transfer/",
        views.transfer_occupant,
        name="transfer_occupant",
    ),
    path(
        "actions/housing/<uuid:pk>/transfer/",
        views.transfer_occupant,
        name="transfer_occupant_legacy",
    ),
    # Registry CRUD
    path(
        "<str:model>/<str:action>/",
        NAMUBUYA.as_view(),
        name="registry-list",
    ),
    path(
        "<str:model>/<str:pk>/<str:action>/",
        NAMUBUYA.as_view(),
        name="registry-object",
    ),
    path(
        "<str:app_label>/<str:model_name>/schema/",
        fields_schema,
        name="fields_schema",
    ),
    path(
        "<str:app_label>/<str:model>/<str:action>/",
        registry_router,
        name="registry_router",
    ),
    path(
        "<str:app_label>/<str:model>/<str:pk>/<str:action>/",
        registry_router,
        name="registry_router_object",
    ),
]
