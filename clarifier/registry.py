import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "clarifier"

# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================

def get_model(name: str):
    """
    Lazy model resolver.

    Prevents circular imports during app loading.
    """
    return apps.get_model(APP_LABEL, name)


# ==========================================================
# MODEL REFERENCES
# ==========================================================

Clarifier = get_model("Clarifier")

ClarifierValve = get_model("ClarifierValve")

ValveOperation = get_model("ValveOperation")

ValveMaintenance = get_model("ValveMaintenance")

ValveInspection = get_model("ValveInspection")

ClarifierSensor = get_model("ClarifierSensor")

SensorReading = get_model("SensorReading")

SludgeBlanketMeasurement = get_model(
    "SludgeBlanketMeasurement"
)

ClarifierPerformance = get_model(
    "ClarifierPerformance"
)


# ==========================================================
# ICON MAP
# ==========================================================

ICONS = {

    "Clarifier": "arrows-spin",

    "ClarifierValve": "faucet-drip",

    "ValveOperation": "right-left",

    "ValveMaintenance": "screwdriver-wrench",

    "ValveInspection": "clipboard-check",

    "ClarifierSensor": "microchip",

    "SensorReading": "chart-line",

    "SludgeBlanketMeasurement": "layer-group",

    "ClarifierPerformance": "gauge-high",

}


# ==========================================================
# GROUP MAP
# ==========================================================

GROUPS = {

    "Clarifier": "assets",

    "ClarifierValve": "assets",

    "ValveOperation": "operations",

    "ValveMaintenance": "maintenance",

    "ValveInspection": "maintenance",

    "ClarifierSensor": "scada",

    "SensorReading": "scada",

    "SludgeBlanketMeasurement": "process",

    "ClarifierPerformance": "analytics",

}


# ==========================================================
# DISPLAY HELPERS
# ==========================================================

def humanize_model_name(model) -> str:

    return re.sub(
        r"(?<!^)(?=[A-Z])",
        " ",
        model.__name__,
    ).strip()


def build_meta(model) -> Dict[str, Any]:

    verbose = humanize_model_name(model)

    return {

        "key":
            f"{model._meta.app_label}."
            f"{model._meta.model_name}",

        "app_label":
            model._meta.app_label,

        "model_name":
            model._meta.model_name,

        "verbose_name":
            verbose,

        "verbose_name_plural":
            f"{verbose}s",

    }


# ==========================================================
# QUERYSET FACTORIES
# ==========================================================

def clarifier_qs(model) -> QuerySet:

    return (
        model.objects
        .select_related(
            "treatment_plant",
            "phase",
        )
        .prefetch_related(
            "valves",
            "sensors",
        )
    )


def valve_qs(model) -> QuerySet:

    return (
        model.objects
        .select_related(
            "clarifier",
        )
        .prefetch_related(
            "operations",
            "maintenance_records",
            "inspections",
        )
    )


def valve_operation_qs(model) -> QuerySet:

    return (
        model.objects
        .select_related(
            "valve",
            "operator",
        )
    )


def maintenance_qs(model) -> QuerySet:

    return (
        model.objects
        .select_related(
            "valve",
            "technician",
        )
    )


def inspection_qs(model) -> QuerySet:

    return (
        model.objects
        .select_related(
            "valve",
            "inspector",
        )
    )


def sensor_qs(model) -> QuerySet:

    return (
        model.objects
        .select_related(
            "clarifier",
        )
    )


def reading_qs(model) -> QuerySet:

    return (
        model.objects
        .select_related(
            "sensor",
        )
    )


def sludge_qs(model) -> QuerySet:

    return (
        model.objects
        .select_related(
            "clarifier",
        )
    )


def performance_qs(model) -> QuerySet:

    return (
        model.objects
        .select_related(
            "clarifier",
        )
    )


# ==========================================================
# REGISTRATION WRAPPER
# ==========================================================

def safe_register(model, **kwargs):

    if model is None:
        raise RuntimeError(
            "Model resolution failed."
        )

    meta = kwargs.get("meta", {})

    meta.update(
        build_meta(model)
    )

    kwargs["meta"] = meta

    ui = kwargs.get("ui", {})

    ui.setdefault(
        "icon",
        ICONS.get(
            model.__name__,
            "cube",
        ),
    )

    ui.setdefault(
        "group",
        GROUPS.get(
            model.__name__,
            "general",
        ),
    )

    kwargs["ui"] = ui

    kwargs.pop(
        "templates",
        None,
    )

    try:

        return register_model(
            **kwargs
        )(model)

    except Exception:

        logger.exception(
            "[clarifier.registry] "
            "Failed registering %s",
            model,
        )

        raise
# ==========================================================
# CLARIFIER
# ==========================================================

safe_register(
    Clarifier,
    search_fields=[
        "name",
        "uuid",
        "serial_number",
    ],
    filter_fields=[
        "treatment_plant",
        "phase",
        "status",
        "design",
        "flow_type",
        "active",
        "automatic_operation",
    ],
    ordering=[
        "treatment_plant",
        "name",
    ],
    select_related=[
        "treatment_plant",
        "phase",
    ],
    prefetch_related=[
        "valves",
        "sensors",
    ],
    queryset_factory=clarifier_qs,
    inline_edit_fields=[
        "status",
        "priority",
        "current_flow",
        "operating_capacity",
        "automatic_operation",
        "active",
    ],
    bulk_actions={
        "enable": True,
        "disable": True,
        "schedule_maintenance": True,
        "export": True,
    },
)


# ==========================================================
# CLARIFIER VALVE
# ==========================================================

safe_register(
    ClarifierValve,
    search_fields=[
        "name",
        "uuid",
        "valve_number",
        "manufacturer",
        "serial_number",
    ],
    filter_fields=[
        "clarifier",
        "valve_type",
        "status",
        "actuator",
        "automatic",
        "active",
    ],
    ordering=[
        "clarifier",
        "valve_number",
    ],
    select_related=[
        "clarifier",
    ],
    queryset_factory=valve_qs,
    inline_edit_fields=[
        "status",
        "opening_percent",
        "automatic",
        "remote_enabled",
        "communication_ok",
        "active",
    ],
    bulk_actions={
        "open": True,
        "close": True,
        "lock": True,
        "unlock": True,
        "schedule_service": True,
    },
)


# ==========================================================
# VALVE OPERATION
# ==========================================================

safe_register(
    ValveOperation,
    search_fields=[
        "valve__name",
        "operator__username",
        "remarks",
    ],
    filter_fields=[
        "operation",
        "successful",
        "automatic",
        "scada_generated",
        "operator",
    ],
    ordering=[
        "-created_at",
    ],
    select_related=[
        "valve",
        "operator",
    ],
    queryset_factory=valve_operation_qs,
    readonly_fields=[
        "created_at",
    ],
)


# ==========================================================
# VALVE MAINTENANCE
# ==========================================================

safe_register(
    ValveMaintenance,
    search_fields=[
        "valve__name",
        "technician__username",
        "work_done",
        "recommendations",
    ],
    filter_fields=[
        "maintenance_type",
        "completed",
        "technician",
    ],
    ordering=[
        "-service_date",
    ],
    select_related=[
        "valve",
        "technician",
    ],
    queryset_factory=maintenance_qs,
    inline_edit_fields=[
        "completed",
        "next_service",
        "recommendations",
    ],
    bulk_actions={
        "mark_completed": True,
    },
)


# ==========================================================
# VALVE INSPECTION
# ==========================================================

safe_register(
    ValveInspection,
    search_fields=[
        "valve__name",
        "inspector__username",
        "remarks",
    ],
    filter_fields=[
        "passed",
        "inspection_date",
        "inspector",
    ],
    ordering=[
        "-inspection_date",
    ],
    select_related=[
        "valve",
        "inspector",
    ],
    queryset_factory=inspection_qs,
    inline_edit_fields=[
        "passed",
        "remarks",
    ],
)