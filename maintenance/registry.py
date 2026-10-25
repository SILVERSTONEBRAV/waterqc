# maintenance/registry.py — unified Maintenance facade registry
import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "maintenance"


def get_model(app_label: str, name: str):
    try:
        return apps.get_model(app_label, name)
    except LookupError:
        logger.exception("[maintenance.registry] Failed resolving %s.%s", app_label, name)
        return None


ICONS = {
    "Location": "map-location-dot",
    "DutyHouse": "house",
    "DutyHouseUnit": "door-open",
    "DutyHouseOccupancy": "bed",
    "OccupancyTransfer": "right-left",
    "WorkRequest": "clipboard-list",
    "WorkOrder": "wrench",
    "WorkTask": "list-check",
    "WorkMaterialUsage": "boxes-stacked",
    "WorkLog": "scroll",
    "WorkCost": "coins",
    "SLARecord": "stopwatch",
    "MaintenanceIncident": "triangle-exclamation",
    "IncidentCluster": "layer-group",
    "IncidentStream": "wave-square",
    "IncidentEscalationRule": "bell",
    "EquipmentHealthScore": "gauge-high",
}

GROUPS = {
    "Location": "housing",
    "DutyHouse": "housing",
    "DutyHouseUnit": "housing",
    "DutyHouseOccupancy": "housing",
    "OccupancyTransfer": "housing",
    "WorkRequest": "work",
    "WorkOrder": "work",
    "WorkTask": "work",
    "WorkMaterialUsage": "work",
    "WorkLog": "work",
    "WorkCost": "work",
    "SLARecord": "sla",
    "MaintenanceIncident": "incidents",
    "IncidentCluster": "incidents",
    "IncidentStream": "incidents",
    "IncidentEscalationRule": "incidents",
    "EquipmentHealthScore": "incidents",
}

GLOBAL_HIDDEN_FIELDS = {
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
}


def humanize_model_name(model) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", model.__name__).strip()


def build_meta(model) -> Dict[str, Any]:
    verbose = humanize_model_name(model)
    return {
        "key": f"{model._meta.app_label}.{model._meta.model_name}",
        "app_label": model._meta.app_label,
        "model_name": model._meta.model_name,
        "verbose_name": verbose,
        "verbose_name_plural": str(
            getattr(model._meta, "verbose_name_plural", f"{verbose}s")
        ),
        "label": verbose,
        "label_plural": str(
            getattr(model._meta, "verbose_name_plural", f"{verbose}s")
        ),
        "has_create": True,
        "has_export": True,
        "has_inline": True,
        "icon": ICONS.get(model.__name__, "cube"),
    }


def safe_register(model, **kwargs):
    if model is None:
        return

    meta = kwargs.pop("meta", {}) or {}
    meta.update(build_meta(model))
    # Keep real app_label for CRUD routes; dashboard uses Maintenance facade URLs.
    ui = kwargs.pop("ui", {}) or {}
    ui.setdefault("icon", ICONS.get(model.__name__, "cube"))
    ui.setdefault("group", GROUPS.get(model.__name__, "general"))

    hidden = set(kwargs.pop("hidden_fields", None) or []) | GLOBAL_HIDDEN_FIELDS

    def filt(fields):
        return [f for f in (fields or []) if f not in hidden]

    try:
        register_model(
            search_fields=filt(kwargs.pop("search_fields", None)),
            filter_fields=filt(kwargs.pop("filter_fields", None)),
            ordering=filt(kwargs.pop("ordering", None)),
            inline_edit_fields=filt(kwargs.pop("inline_edit_fields", None)),
            select_related=kwargs.pop("select_related", None) or [],
            prefetch_related=kwargs.pop("prefetch_related", None) or [],
            queryset_factory=kwargs.pop("queryset_factory", None),
            bulk_actions=kwargs.pop("bulk_actions", None) or {},
            permissions=kwargs.pop("permissions", None) or {},
            meta=meta,
            ui=ui,
            **kwargs,
        )(model)
    except Exception:
        logger.exception("[maintenance.registry] failed %s", model.__name__)

def bootstrap_maintenance_registry():
    Location = get_model("duty_house", "Location")
    DutyHouse = get_model("duty_house", "DutyHouse")
    DutyHouseUnit = get_model("duty_house", "DutyHouseUnit")
    DutyHouseOccupancy = get_model("duty_house", "DutyHouseOccupancy")
    OccupancyTransfer = get_model("duty_house", "OccupancyTransfer")
    WorkRequest = get_model("maintenance", "WorkRequest")
    WorkOrder = get_model("maintenance", "WorkOrder")
    WorkTask = get_model("maintenance", "WorkTask")
    WorkMaterialUsage = get_model("maintenance", "WorkMaterialUsage")
    WorkLog = get_model("maintenance", "WorkLog")
    WorkCost = get_model("maintenance", "WorkCost")
    SLARecord = get_model("maintenance", "SLARecord")
    MaintenanceIncident = get_model("Maintenance_Incident", "MaintenanceIncident")
    IncidentCluster = get_model("Maintenance_Incident", "IncidentCluster")
    IncidentStream = get_model("Maintenance_Incident", "IncidentStream")
    IncidentEscalationRule = get_model("Maintenance_Incident", "IncidentEscalationRule")
    EquipmentHealthScore = get_model("Maintenance_Incident", "EquipmentHealthScore")

    safe_register(
        Location,
        search_fields=["name", "code", "plant__name"],
        filter_fields=["plant", "location_type", "is_active"],
        ordering=["name"],
        select_related=["plant"],
    )
    safe_register(
        DutyHouse,
        search_fields=["house_number", "name", "plant__name"],
        filter_fields=["plant", "status", "is_active"],
        ordering=["house_number"],
        select_related=["plant", "location"],
    )
    safe_register(
        DutyHouseUnit,
        search_fields=["unit_number", "duty_house__house_number"],
        filter_fields=["duty_house", "status", "unit_type"],
        ordering=["unit_number"],
        select_related=["duty_house"],
    )
    safe_register(
        DutyHouseOccupancy,
        search_fields=["user__username", "unit__unit_number"],
        filter_fields=["status", "is_current"],
        ordering=["-start_date"],
        select_related=["duty_house", "unit", "user"],
    )
    safe_register(
        OccupancyTransfer,
        search_fields=["user__username"],
        ordering=["-transferred_at"],
        select_related=["from_unit", "to_unit", "user"],
    )
    safe_register(
        WorkRequest,
        search_fields=["title", "priority", "status"],
        filter_fields=["status", "priority", "is_emergency"],
        ordering=["-created_at"],
        select_related=["reported_by", "duty_house", "approved_by"],
    )
    safe_register(
        WorkOrder,
        search_fields=["status", "priority"],
        filter_fields=["status", "priority"],
        ordering=["-created_at"],
        select_related=["request", "duty_house", "assigned_to"],
    )
    safe_register(
        WorkTask,
        search_fields=["title", "status"],
        filter_fields=["status"],
        ordering=["-created_at"],
        select_related=["order", "assigned_to"],
    )
    safe_register(WorkMaterialUsage, ordering=["-created_at"], select_related=["order"])
    safe_register(WorkLog, ordering=["-created_at"], select_related=["order"])
    safe_register(WorkCost, ordering=["-created_at"], select_related=["order"])
    safe_register(
        SLARecord,
        search_fields=["status"],
        filter_fields=["status"],
        ordering=["-created_at"],
        select_related=["request"],
    )
    safe_register(
        MaintenanceIncident,
        search_fields=[
            "incident_no", "title", "severity", "status", "root_cause",
            "resolution_summary", "assigned_to__username",
        ],
        filter_fields=["severity", "status", "incident_type", "plant", "assigned_to"],
        ordering=["-reported_at"],
        select_related=[
            "reported_by", "assigned_to", "equipment", "plant", "duty_house", "cluster"
        ],
    )
    safe_register(IncidentCluster, ordering=["-frequency_score"])
    safe_register(IncidentStream, ordering=["-created_at"], select_related=["incident"])
    safe_register(
        IncidentEscalationRule,
        filter_fields=["severity", "is_active"],
        ordering=["severity"],
    )
    safe_register(EquipmentHealthScore, ordering=["score"], select_related=["equipment"])
    logger.info("[maintenance.registry] unified bootstrap complete")


# Bootstrap runs from MaintenanceConfig.ready() to avoid double-registration.
