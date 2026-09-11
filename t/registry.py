# t/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "t"


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
TreatmentPlant = get_model("TreatmentPlant")
TreatmentPlantPhase = get_model("TreatmentPlantPhase")
FilterType = get_model("FilterType")
WaterFilter = get_model("WaterFilter")
Status = get_model("Status")
Clarifier = get_model("Clarifier")
DisludgeValve = get_model("DisludgeValve")

TreatedWaterLimit = get_model("TreatedWaterLimit")
MicrobialLimit = get_model("MicrobialLimit")
HeavyMetalLimit = get_model("HeavyMetalLimit")
RawWaterLimit = get_model("RawWaterLimit")
ClarifiedWaterLimit = get_model("ClarifiedWaterLimit")
CoagulatedWaterLimit = get_model("CoagulatedWaterLimit")
FilteredWaterLimit = get_model("FilteredWaterLimit")


# ==========================================================
# ICON MAP (NO DUPLICATES)
# ==========================================================
ICONS = {
    "TreatmentPlant": "industry",
    "TreatmentPlantPhase": "layer-group",
    "FilterType": "sliders",
    "WaterFilter": "filter-circle-xmark",
    "Status": "traffic-light",
    "Clarifier": "arrows-spin",
    "DisludgeValve": "faucet-drip",

    "TreatedWaterLimit": "glass-water",
    "MicrobialLimit": "bacteria",
    "HeavyMetalLimit": "atom",
    "RawWaterLimit": "water",
    "ClarifiedWaterLimit": "droplet",
    "CoagulatedWaterLimit": "flask",
    "FilteredWaterLimit": "filter",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "TreatmentPlant": "plants",
    "TreatmentPlantPhase": "plants",

    "FilterType": "filters",
    "WaterFilter": "filters",

    "Status": "system",

    "Clarifier": "clarification",
    "DisludgeValve": "clarification",

    "TreatedWaterLimit": "limits",
    "MicrobialLimit": "limits",
    "HeavyMetalLimit": "limits",
    "RawWaterLimit": "limits",
    "ClarifiedWaterLimit": "limits",
    "CoagulatedWaterLimit": "limits",
    "FilteredWaterLimit": "limits",
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
def plant_qs(model) -> QuerySet:
    return model.objects.prefetch_related(
        "phases",
        "filters",
        "clarifiers",
    )


def phase_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
    )


def filter_qs(model) -> QuerySet:
    return model.objects.select_related(
        "filter_type",
        "treatment_plant",
        "phase",
    )


def clarifier_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "phase",
    )


def valve_qs(model) -> QuerySet:
    return model.objects.select_related(
        "clarifier",
        "status",
    )


def limit_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "parameter",
    )


# ==========================================================
# SHARED CONFIG
# ==========================================================
LIMIT_BASE_CONFIG = {
    "search_fields": [
        "treatment_plant__name",
        "parameter__name",
    ],
    "filter_fields": [
        "treatment_plant",
        "parameter",
    ],
    "ordering": [
        "treatment_plant",
    ],
    "inline_edit_fields": [
        "min_value",
        "max_value",
    ],
    "queryset_factory": limit_qs,
}


# ==========================================================
# REGISTRATION WRAPPER
# ==========================================================
def safe_register(model, **kwargs):
    """
    Registry normalization layer.
    """

    if model is None:
        raise RuntimeError(
            "Model resolution failed."
        )

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
        GROUPS.get(model.__name__, "general"),
    )

    kwargs["ui"] = ui

    kwargs.pop("templates", None)

    try:
        return register_model(**kwargs)(model)
    except Exception:
        logger.exception(
            "[t.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# CORE MODELS
# ==========================================================
safe_register(
    TreatmentPlant,
    search_fields=["name", "code", "location"],
    filter_fields=["code", "location"],
    ordering=["name"],
    prefetch_related=[
        "phases",
        "filters",
        "clarifiers",
    ],
    queryset_factory=plant_qs,
    inline_edit_fields=[
        "name",
        "code",
        "location",
    ],
    bulk_actions={
        "delete_selected": True,
    },
)

safe_register(
    TreatmentPlantPhase,
    search_fields=["name"],
    filter_fields=["treatment_plant"],
    ordering=["name"],
    select_related=["treatment_plant"],
    queryset_factory=phase_qs,
    inline_edit_fields=[
        "name",
        "design_capacity",
        "operational_capacity",
    ],
)

safe_register(
    FilterType,
    search_fields=["name"],
    ordering=["name"],
    inline_edit_fields=["name"],
)

safe_register(
    WaterFilter,
    search_fields=[
        "name",
        "location",
    ],
    filter_fields=[
        "status",
        "filter_type",
        "treatment_plant",
    ],
    ordering=["name"],
    select_related=[
        "filter_type",
        "treatment_plant",
        "phase",
    ],
    queryset_factory=filter_qs,
    inline_edit_fields=[
        "name",
        "status",
        "flow_rate",
        "last_maintenance_date",
        "treatment_plant",
        "phase",
    ],
    bulk_actions={
        "backwash": True,
        "mark_maintenance": True,
    },
)

safe_register(
    Status,
    search_fields=["name"],
    ordering=["name"],
    inline_edit_fields=["name"],
)

safe_register(
    Clarifier,
    search_fields=["name"],
    filter_fields=[
        "treatment_plant",
        "flow_type",
        "design",
    ],
    ordering=["name"],
    select_related=[
        "treatment_plant",
        "phase",
    ],
    queryset_factory=clarifier_qs,
    inline_edit_fields=[
        "name",
        "design_capacity",
        "flow_type",
        "design",
        "surface_loading",
    ],
)

safe_register(
    DisludgeValve,
    search_fields=["name"],
    filter_fields=[
        "clarifier",
        "status",
    ],
    ordering=["name"],
    select_related=[
        "clarifier",
        "status",
    ],
    queryset_factory=valve_qs,
    inline_edit_fields=[
        "name",
        "status",
    ],
)


# ==========================================================
# LIMIT FACTORY
# ==========================================================
def register_limit(
    model,
    display_name: str,
):
    config = LIMIT_BASE_CONFIG.copy()

    config["meta"] = {
        "verbose_name": display_name,
    }

    safe_register(
        model,
        **config,
    )


register_limit(
    TreatedWaterLimit,
    "Treated Water Limit",
)

register_limit(
    MicrobialLimit,
    "Microbial Limit",
)

register_limit(
    HeavyMetalLimit,
    "Heavy Metal Limit",
)

register_limit(
    RawWaterLimit,
    "Raw Water Limit",
)

register_limit(
    ClarifiedWaterLimit,
    "Clarified Water Limit",
)

register_limit(
    CoagulatedWaterLimit,
    "Coagulated Water Limit",
)

register_limit(
    FilteredWaterLimit,
    "Filtered Water Limit",
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[t.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[t.registry] registry unavailable during import"
    )