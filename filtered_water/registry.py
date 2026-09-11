# filtered_water/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "filtered_water"


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
FilteredWaterAnalysis = get_model("FilteredWaterAnalysis")
FilteredWaterResults = get_model("FilteredWaterResults")
FilteredWaterAnalysisTransition = get_model(
    "FilteredWaterAnalysisTransition"
)


# ==========================================================
# ICONS
# ==========================================================
ICONS = {
    "FilteredWaterAnalysis": "glass-water",
    "FilteredWaterResults": "vial",
    "FilteredWaterAnalysisTransition": "timeline",
}


# ==========================================================
# GROUPS
# ==========================================================
GROUPS = {
    "FilteredWaterAnalysis": "analysis",
    "FilteredWaterResults": "analysis",
    "FilteredWaterAnalysisTransition": "audit",
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
def analysis_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "treatment_plant",
            "treatment_plant_phase",
            "analysed_by",
            "verified_by",
        )
        .prefetch_related(
            "results",
            "transitions",
        )
    )


def result_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "analysis",
            "water_filter",
            "parameter",
            "parameter__parameter",
        )
    )


def transition_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "analysis",
            "performed_by",
        )
    )


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
            "[filtered_water.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# FILTERED WATER ANALYSIS
# ==========================================================
safe_register(
    FilteredWaterAnalysis,
    search_fields=[
        "uuid",
        "remarks",
        "treatment_plant__name",
        "treatment_plant_phase__name",
    ],
    filter_fields=[
        "state",
        "treatment_plant",
        "treatment_plant_phase",
        "timestamp",
    ],
    ordering=[
        "-timestamp",
        "-created_at",
    ],
    select_related=[
        "treatment_plant",
        "treatment_plant_phase",
        "analysed_by",
        "verified_by",
    ],
    prefetch_related=[
        "results",
        "transitions",
    ],
    queryset_factory=analysis_qs,
    inline_edit_fields=[
        "remarks",
        "state",
    ],
    bulk_actions={
        "verify": True,
        "export": True,
    },
)


# ==========================================================
# FILTERED WATER RESULTS
# ==========================================================
safe_register(
    FilteredWaterResults,
    search_fields=[
        "analysis__uuid",
        "water_filter__name",
        "parameter__parameter__name",
    ],
    filter_fields=[
        "analysis",
        "water_filter",
        "parameter",
    ],
    ordering=[
        "analysis",
        "water_filter",
        "parameter",
    ],
    select_related=[
        "analysis",
        "water_filter",
        "parameter",
        "parameter__parameter",
    ],
    queryset_factory=result_qs,
    inline_edit_fields=[
        "result_value",
    ],
)


# ==========================================================
# TRANSITIONS
# ==========================================================
safe_register(
    FilteredWaterAnalysisTransition,
    search_fields=[
        "analysis__uuid",
        "from_state",
        "to_state",
        "performed_by__username",
    ],
    filter_fields=[
        "from_state",
        "to_state",
        "performed_by",
    ],
    ordering=[
        "-transition_time",
    ],
    select_related=[
        "analysis",
        "performed_by",
    ],
    queryset_factory=transition_qs,
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[filtered_water.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[filtered_water.registry] registry unavailable during import"
    )