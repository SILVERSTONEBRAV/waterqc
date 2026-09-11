# maintenance_incident/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "Maintenance_Incident"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================
def get_model(name: str):
    """
    Lazy model resolver (prevents circular imports).
    """
    return apps.get_model(APP_LABEL, name)


# ==========================================================
# MODEL REFERENCES
# ==========================================================
MaintenanceIncident = get_model("MaintenanceIncident")
IncidentCluster = get_model("IncidentCluster")
IncidentStream = get_model("IncidentStream")
IncidentEscalationRule = get_model("IncidentEscalationRule")
EquipmentHealthScore = get_model("EquipmentHealthScore")


# ==========================================================
# ICON MAP (SCADA / MAINTENANCE DOMAIN)
# ==========================================================
ICONS = {
    "MaintenanceIncident": "triangle-exclamation",
    "IncidentCluster": "layer-group",
    "IncidentStream": "wave-square",
    "IncidentEscalationRule": "bell",
    "EquipmentHealthScore": "gauge-high",
}


# ==========================================================
# GROUP MAP (SCADA ORGANIZATION LAYER)
# ==========================================================
GROUPS = {
    "MaintenanceIncident": "incidents",
    "IncidentCluster": "analytics",
    "IncidentStream": "realtime",
    "IncidentEscalationRule": "rules",
    "EquipmentHealthScore": "predictive-maintenance",
}


# ==========================================================
# DISPLAY HELPERS
# ==========================================================
def humanize_model_name(model) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", model.__name__).strip()


def build_meta(model) -> Dict[str, Any]:
    verbose = humanize_model_name(model)

    return {
        "key": f"{model._meta.app_label}.{model._meta.model_name}",
        "app_label": model._meta.app_label,
        "model_name": model._meta.model_name,
        "verbose_name": verbose,
        "verbose_name_plural": f"{verbose}s",
    }


# ==========================================================
# QUERYSET FACTORIES (SCADA OPTIMIZED)
# ==========================================================
def incident_qs(model) -> QuerySet:
    return model.objects.select_related(
        "reported_by",
        "equipment",
        "plant",
        "cluster",
        "work_order",
    ).prefetch_related(
        "stream_events"
    )


def cluster_qs(model) -> QuerySet:
    return model.objects.prefetch_related()


def stream_qs(model) -> QuerySet:
    return model.objects.select_related("incident")


def rule_qs(model) -> QuerySet:
    return model.objects.all()


def health_qs(model) -> QuerySet:
    return model.objects.select_related("equipment")


# ==========================================================
# REGISTRY WRAPPER
# ==========================================================
def safe_register(model, **kwargs):
    """
    Normalized registry layer (consistent across all apps).
    """

    if model is None:
        raise RuntimeError("Model resolution failed.")

    meta = kwargs.get("meta", {})
    meta.update(build_meta(model))
    kwargs["meta"] = meta

    ui = kwargs.get("ui", {})
    ui.setdefault("icon", ICONS.get(model.__name__, "cube"))
    ui.setdefault("group", GROUPS.get(model.__name__, "general"))
    kwargs["ui"] = ui

    kwargs.pop("templates", None)

    try:
        return register_model(**kwargs)(model)
    except Exception:
        logger.exception(
            "[maintenance_incident.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# INCIDENT CORE REGISTRATION
# ==========================================================
safe_register(
    MaintenanceIncident,
    search_fields=[
        "incident_no",
        "title",
        "incident_type",
        "severity",
        "status",
        "equipment__name",
        "plant__name",
    ],
    filter_fields=[
        "severity",
        "status",
        "incident_type",
        "plant",
    ],
    ordering=["-created_at"],
    queryset_factory=incident_qs,
    select_related=[
        "reported_by",
        "equipment",
        "plant",
        "cluster",
    ],
    bulk_actions={
        "review": True,
        "confirm": True,
        "resolve": True,
        "close": True,
        "auto_dispatch": True,
    },
)


# ==========================================================
# CLUSTERING / ANALYTICS
# ==========================================================
safe_register(
    IncidentCluster,
    search_fields=[
        "cluster_key",
        "title",
        "incident_type",
    ],
    filter_fields=[
        "incident_type",
    ],
    ordering=["-frequency_score"],
    queryset_factory=cluster_qs,
)


# ==========================================================
# REALTIME STREAM
# ==========================================================
safe_register(
    IncidentStream,
    search_fields=[
        "event_type",
        "incident__incident_no",
    ],
    filter_fields=[
        "event_type",
        "severity_snapshot",
    ],
    ordering=["-created_at"],
    queryset_factory=stream_qs,
    select_related=["incident"],
)


# ==========================================================
# ESCALATION RULES
# ==========================================================
safe_register(
    IncidentEscalationRule,
    search_fields=[
        "name",
        "incident_type",
        "severity",
    ],
    filter_fields=[
        "severity",
        "incident_type",
        "is_active",
    ],
    ordering=["severity"],
    queryset_factory=rule_qs,
)


# ==========================================================
# EQUIPMENT HEALTH (PREDICTIVE MAINTENANCE)
# ==========================================================
safe_register(
    EquipmentHealthScore,
    search_fields=[
        "equipment__name",
    ],
    filter_fields=[
        "score",
    ],
    ordering=["score"],
    queryset_factory=health_qs,
    select_related=[
        "equipment",
    ],
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[maintenance_incident.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[maintenance_incident.registry] registry unavailable during import"
    )