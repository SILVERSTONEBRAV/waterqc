# itinerary/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "itinerary"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================
def get_model(name: str):
    return apps.get_model(APP_LABEL, name)


# ==========================================================
# MODEL REFERENCES
# ==========================================================
SystemConfig = get_model("SystemConfig")
SamplingPlan = get_model("SamplingPlan")

RegionSamplingPoint = get_model("RegionSamplingPoint")
FCARegionSamplingPoint = get_model("FCARegionSamplingPoint")
Catchment = get_model("Catchment")
CatchmentSamplingPoint = get_model("CatchmentSamplingPoint")

DynamicSamplingPoint = get_model("DynamicSamplingPoint")
Itinerary = get_model("Itinerary")
SampleCategory = get_model("SampleCategory")


# ==========================================================
# ICONS
# ==========================================================
ICONS = {
    "SystemConfig": "gear",

    "SamplingPlan": "calendar-days",

    "RegionSamplingPoint": "map-location-dot",
    "FCARegionSamplingPoint": "map",
    "Catchment": "mountain",
    "CatchmentSamplingPoint": "location-dot",

    "DynamicSamplingPoint": "location-crosshairs",

    "Itinerary": "route",

    "SampleCategory": "tags",
}


# ==========================================================
# GROUPS
# ==========================================================
GROUPS = {
    "SystemConfig": "system",

    "SamplingPlan": "planning",

    "RegionSamplingPoint": "sampling-points",
    "FCARegionSamplingPoint": "sampling-points",
    "Catchment": "sampling-points",
    "CatchmentSamplingPoint": "sampling-points",
    "DynamicSamplingPoint": "sampling-points",

    "Itinerary": "operations",

    "SampleCategory": "configuration",
}


# ==========================================================
# DISPLAY HELPERS
# ==========================================================
def humanize_model_name(model):
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
def plan_qs(model) -> QuerySet:
    return model.objects.prefetch_related(
        "dynamicsamplingpoint_set"
    )


def itinerary_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "content_type"
        )
        .prefetch_related(
            "sampling_points",
            "sampling_points__content_type",
        )
    )


def region_point_qs(model):
    return model.objects.select_related(
        "region"
    )


def catchment_point_qs(model):
    return model.objects.select_related(
        "catchment"
    )


def dynamic_point_qs(model):
    return model.objects.select_related(
        "content_type"
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
            "[itinerary.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# SYSTEM CONFIG
# ==========================================================
safe_register(
    SystemConfig,
    search_fields=[
        "key",
    ],
    ordering=[
        "key",
    ],
    inline_edit_fields=[
        "key",
        "value",
    ],
)


# ==========================================================
# SAMPLING PLAN
# ==========================================================
safe_register(
    SamplingPlan,
    search_fields=[
        "notes",
    ],
    ordering=[
        "-month",
    ],
    queryset_factory=plan_qs,
    inline_edit_fields=[
        "target_sampling_points",
        "notes",
    ],
    bulk_actions={
        "refresh_actuals": True,
    },
)


# ==========================================================
# REGION SAMPLING POINT
# ==========================================================
safe_register(
    RegionSamplingPoint,
    search_fields=[
        "name",
        "region__name",
    ],
    filter_fields=[
        "preferred_frequency",
        "is_deleted",
        "region",
    ],
    ordering=[
        "name",
    ],
    select_related=[
        "region",
    ],
    queryset_factory=region_point_qs,
    inline_edit_fields=[
        "name",
        "preferred_frequency",
        "attributes",
        "location",
    ],
)


# ==========================================================
# FCA REGION SAMPLING POINT
# ==========================================================
safe_register(
    FCARegionSamplingPoint,
    search_fields=[
        "name",
        "fca_region_name",
    ],
    filter_fields=[
        "preferred_frequency",
        "is_deleted",
    ],
    ordering=[
        "name",
    ],
    inline_edit_fields=[
        "name",
        "fca_region_name",
        "preferred_frequency",
        "location",
        "attributes",
    ],
)


# ==========================================================
# CATCHMENT
# ==========================================================
safe_register(
    Catchment,
    search_fields=[
        "name",
        "treatment_plant_name",
    ],
    ordering=[
        "name",
    ],
    inline_edit_fields=[
        "name",
        "treatment_plant_name",
    ],
)


# ==========================================================
# CATCHMENT SAMPLING POINT
# ==========================================================
safe_register(
    CatchmentSamplingPoint,
    search_fields=[
        "name",
        "catchment__name",
    ],
    filter_fields=[
        "catchment",
        "preferred_frequency",
        "is_deleted",
    ],
    ordering=[
        "name",
    ],
    select_related=[
        "catchment",
    ],
    queryset_factory=catchment_point_qs,
    inline_edit_fields=[
        "name",
        "preferred_frequency",
        "location",
        "attributes",
    ],
)


# ==========================================================
# DYNAMIC SAMPLING POINT
# ==========================================================
safe_register(
    DynamicSamplingPoint,
    ordering=[
        "object_id",
    ],
    select_related=[
        "content_type",
    ],
    queryset_factory=dynamic_point_qs,
)


# ==========================================================
# ITINERARY
# ==========================================================
safe_register(
    Itinerary,
    search_fields=[
        "name",
        "remarks",
    ],
    filter_fields=[
        "status",
        "sampling_date",
        "is_locked",
        "assignment_strategy",
    ],
    ordering=[
        "-sampling_date",
    ],
    select_related=[
        "content_type",
    ],
    prefetch_related=[
        "sampling_points",
        "sampling_points__content_type",
    ],
    queryset_factory=itinerary_qs,
    inline_edit_fields=[
        "name",
        "sampling_date",
        "status",
        "remarks",
        "assignment_strategy",
        "max_sampling_points",
    ],
    bulk_actions={
        "lock": True,
        "complete": True,
        "assign_points": True,
    },
)


# ==========================================================
# SAMPLE CATEGORY
# ==========================================================
safe_register(
    SampleCategory,
    search_fields=[
        "name",
        "description",
    ],
    filter_fields=[
        "is_active",
    ],
    ordering=[
        "name",
    ],
    inline_edit_fields=[
        "name",
        "description",
        "is_active",
    ],
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[itinerary.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[itinerary.registry] registry unavailable during import"
    )