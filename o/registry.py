# o/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "o"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================
def get_model(name: str):
    """
    Lazy model resolver to avoid circular imports.
    """
    return apps.get_model(APP_LABEL, name)


# ==========================================================
# MODEL REFERENCES
# ==========================================================
MonitoringTime = get_model("MonitoringTime")
ChemicalCategory = get_model("ChemicalCategory")
ChemicalPump = get_model("ChemicalPump")
PumpStatus = get_model("PumpStatus")
ChemicalTank = get_model("ChemicalTank")
ChemicalStock = get_model("ChemicalStock")

CoagulantUsageRecord = get_model("CoagulantUsageRecord")
PHAdjusterUsageRecord = get_model("PHAdjusterUsageRecord")
DisinfectantUsageRecord = get_model("DisinfectantUsageRecord")
FlocculantUsageRecord = get_model("FlocculantUsageRecord")
ChemicalUsageRecord = get_model("ChemicalUsageRecord")

Reservoir = get_model("Reservoir")
ReservoirLevel = get_model("ReservoirLevel")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "MonitoringTime": "clock",
    "ChemicalCategory": "flask",
    "ChemicalPump": "pump-medical",
    "PumpStatus": "circle-exclamation",
    "ChemicalTank": "database",

    "ChemicalStock": "boxes",

    "CoagulantUsageRecord": "water",
    "PHAdjusterUsageRecord": "vial",
    "DisinfectantUsageRecord": "biohazard",
    "FlocculantUsageRecord": "snowflake",
    "ChemicalUsageRecord": "chart-line",

    "Reservoir": "water-ladder",
    "ReservoirLevel": "gauge-high",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "MonitoringTime": "operations",
    "ChemicalCategory": "chemicals",
    "ChemicalPump": "chemicals",
    "PumpStatus": "chemicals",
    "ChemicalTank": "chemicals",
    "ChemicalStock": "chemicals",

    "CoagulantUsageRecord": "usage",
    "PHAdjusterUsageRecord": "usage",
    "DisinfectantUsageRecord": "usage",
    "FlocculantUsageRecord": "usage",
    "ChemicalUsageRecord": "usage",

    "Reservoir": "storage",
    "ReservoirLevel": "storage",
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
        "key": f"{model._meta.app_label}.{model._meta.model_name}",
        "app_label": model._meta.app_label,
        "model_name": model._meta.model_name,
        "verbose_name": verbose,
        "verbose_name_plural": f"{verbose}s",
    }


# ==========================================================
# QUERYSET FACTORIES
# ==========================================================
def pump_qs(model) -> QuerySet:
    return model.objects.select_related(
        "phase",
    )


def pump_status_qs(model) -> QuerySet:
    return model.objects.select_related(
        "pump",
        "treatment_plant",
        "updated_by",
    )


def tank_qs(model) -> QuerySet:
    return model.objects.select_related(
        "phase",
    )


def stock_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "chemical",
    )


def usage_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "phase",
        "chemical",
        "pump_used",
        "tank_used",
        "recorded_by",
        "shift_assignment",
    )


def reservoir_qs(model) -> QuerySet:
    return model.objects.select_related(
        "phase",
    )


def reservoir_level_qs(model) -> QuerySet:
    return model.objects.select_related(
        "reservoir",
        "monitoring_time",
    )


# ==========================================================
# SHARED CONFIG
# ==========================================================
USAGE_BASE_CONFIG = {
    "search_fields": [
        "chemical__name",
        "treatment_plant__name",
    ],
    "filter_fields": [
        "chemical",
        "treatment_plant",
        "phase",
    ],
    "ordering": [
        "-date",
    ],
}


# ==========================================================
# REGISTRATION WRAPPER
# ==========================================================
def safe_register(model, **kwargs):
    """
    Registry normalization layer.
    """

    if model is None:
        raise RuntimeError("Model resolution failed.")

    meta = kwargs.get("meta", {})
    meta.update(build_meta(model))
    kwargs["meta"] = meta

    ui = kwargs.get("ui", {})
    ui.setdefault(
        "icon",
        ICONS.get(model.__name__, "cube"),
    )
    ui.setdefault(
        "group",
        GROUPS.get(model.__name__, "operations"),
    )

    kwargs["ui"] = ui

    kwargs.pop("templates", None)

    try:
        return register_model(**kwargs)(model)
    except Exception:
        logger.exception(
            "[o.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# CORE REGISTRATIONS
# ==========================================================

safe_register(
    MonitoringTime,
    ordering=["time"],
    inline_edit_fields=["time"],
)

safe_register(
    ChemicalCategory,
    search_fields=["chemical__name", "category"],
    filter_fields=["chemical", "category"],
    ordering=["chemical"],
    select_related=["chemical"],
)

safe_register(
    ChemicalPump,
    search_fields=["name"],
    filter_fields=["phase", "category"],
    ordering=["name"],
    select_related=["phase"],
    inline_edit_fields=["name", "category"],
)

safe_register(
    PumpStatus,
    search_fields=["status"],
    filter_fields=["status", "treatment_plant"],
    ordering=["-created_at"],
    select_related=["pump", "treatment_plant", "updated_by"],
    queryset_factory=pump_status_qs,
)

safe_register(
    ChemicalTank,
    search_fields=["name"],
    filter_fields=["phase", "category"],
    ordering=["name"],
    select_related=["phase"],
    queryset_factory=tank_qs,
)

safe_register(
    ChemicalStock,
    search_fields=["chemical__name"],
    filter_fields=["treatment_plant", "chemical"],
    ordering=["treatment_plant"],
    select_related=["treatment_plant", "chemical"],
    queryset_factory=stock_qs,
    inline_edit_fields=["quantity_kg"],
)


# ==========================================================
# USAGE RECORDS
# ==========================================================
safe_register(
    CoagulantUsageRecord,
    **USAGE_BASE_CONFIG,
    select_related=["chemical"],
    queryset_factory=usage_qs,
)

safe_register(
    PHAdjusterUsageRecord,
    **USAGE_BASE_CONFIG,
    select_related=["chemical"],
    queryset_factory=usage_qs,
)

safe_register(
    DisinfectantUsageRecord,
    **USAGE_BASE_CONFIG,
    select_related=["chemical"],
    queryset_factory=usage_qs,
)

safe_register(
    FlocculantUsageRecord,
    **USAGE_BASE_CONFIG,
    select_related=["chemical"],
    queryset_factory=usage_qs,
)

safe_register(
    ChemicalUsageRecord,
    search_fields=["chemical__name"],
    filter_fields=["chemical", "treatment_plant", "date_used"],
    ordering=["-date_used"],
    select_related=["chemical", "treatment_plant", "recorded_by"],
)


# ==========================================================
# RESERVOIRS
# ==========================================================
safe_register(
    Reservoir,
    search_fields=["name"],
    filter_fields=["phase"],
    ordering=["name"],
    select_related=["phase"],
    queryset_factory=reservoir_qs,
)

safe_register(
    ReservoirLevel,
    search_fields=["reservoir__name"],
    filter_fields=["reservoir", "date"],
    ordering=["-date"],
    select_related=["reservoir", "monitoring_time"],
    queryset_factory=reservoir_level_qs,
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[o.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[o.registry] registry unavailable during import"
    )