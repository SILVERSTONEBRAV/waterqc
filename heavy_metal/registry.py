# heavy_metal/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "heavy_metal"


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
HeavyMetalSamplingSchedule = get_model("HeavyMetalSamplingSchedule")
HeavyMetalSamplingTime = get_model("HeavyMetalSamplingTime")

HeavyMetalAnalysis = get_model("HeavyMetalAnalysis")
HeavyMetalParameter = get_model("HeavyMetalParameter")

HeavyMetalNonConformity = get_model("HeavyMetalNonConformity")
HeavyMetalNonConformityLog = get_model("HeavyMetalNonConformityLog")
HeavyMetalAnalysisLog = get_model("HeavyMetalAnalysisLog")

Cause = get_model("Cause")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "HeavyMetalSamplingSchedule": "clock",
    "HeavyMetalSamplingTime": "stopwatch",

    "HeavyMetalAnalysis": "flask",
    "HeavyMetalParameter": "vial",

    "HeavyMetalNonConformity": "triangle-exclamation",
    "HeavyMetalNonConformityLog": "clipboard-list",
    "HeavyMetalAnalysisLog": "file-lines",

    "Cause": "diagram-project",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "HeavyMetalSamplingSchedule": "sampling",
    "HeavyMetalSamplingTime": "sampling",

    "HeavyMetalAnalysis": "analysis",
    "HeavyMetalParameter": "analysis",

    "HeavyMetalNonConformity": "quality",
    "HeavyMetalNonConformityLog": "quality",
    "HeavyMetalAnalysisLog": "quality",

    "Cause": "configuration",
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
def schedule_qs(model) -> QuerySet:
    return model.objects.prefetch_related(
        "times",
    )


def sampling_time_qs(model) -> QuerySet:
    return model.objects.select_related(
        "schedule",
    )


def analysis_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "treatment_plant",
            "treatment_plant_phase",
            "sampling_time",
            "shift",
            "analysed_by",
            "verified_by",
            "approved_by",
        )
        .prefetch_related(
            "parameters",
            "logs",
            "nonconformities",
        )
    )


def parameter_qs(model) -> QuerySet:
    return model.objects.select_related(
        "analysis",
        "parameter",
    )


def nonconformity_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "analysis",
            "triggered_by",
            "reviewed_by",
        )
        .prefetch_related(
            "causes",
            "logs",
        )
    )


def analysis_log_qs(model) -> QuerySet:
    return model.objects.select_related(
        "analysis",
        "actor",
    )


def nonconformity_log_qs(model) -> QuerySet:
    return model.objects.select_related(
        "nonconformity",
        "actor",
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
            "[heavy_metal.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# SAMPLING
# ==========================================================
safe_register(
    HeavyMetalSamplingSchedule,
    search_fields=[
        "start_time",
    ],
    ordering=[
        "start_time",
    ],
    prefetch_related=[
        "times",
    ],
    queryset_factory=schedule_qs,
    inline_edit_fields=[
        "start_time",
        "interval_minutes",
        "enabled",
        "adaptive",
    ],
)

safe_register(
    HeavyMetalSamplingTime,
    filter_fields=[
        "schedule",
    ],
    ordering=[
        "time",
    ],
    select_related=[
        "schedule",
    ],
    queryset_factory=sampling_time_qs,
    inline_edit_fields=[
        "time",
    ],
)


# ==========================================================
# ANALYSIS
# ==========================================================
safe_register(
    HeavyMetalAnalysis,
    search_fields=[
        "reference_id",
        "remarks",
        "treatment_plant__name",
        "treatment_plant_phase__name",
    ],
    filter_fields=[
        "state",
        "analysis_date",
        "treatment_plant",
        "treatment_plant_phase",
        "shift",
    ],
    ordering=[
        "-analysis_date",
        "-created_at",
    ],
    select_related=[
        "treatment_plant",
        "treatment_plant_phase",
        "sampling_time",
        "shift",
    ],
    prefetch_related=[
        "parameters",
        "logs",
        "nonconformities",
    ],
    queryset_factory=analysis_qs,
    inline_edit_fields=[
        "state",
        "remarks",
    ],
    bulk_actions={
        "verify": True,
        "approve": True,
        "export": True,
    },
)


safe_register(
    HeavyMetalParameter,
    search_fields=[
        "parameter__parameter__name",
        "analysis__reference_id",
    ],
    filter_fields=[
        "parameter",
        "analysis",
        "manually_editable",
    ],
    ordering=[
        "parameter__parameter__name",
    ],
    select_related=[
        "analysis",
        "parameter",
    ],
    queryset_factory=parameter_qs,
    inline_edit_fields=[
        "value",
        "manually_editable",
    ],
)


# ==========================================================
# NONCONFORMITIES
# ==========================================================
safe_register(
    HeavyMetalNonConformity,
    search_fields=[
        "parameter_name",
        "corrective_action",
        "preventive_action",
        "root_cause",
    ],
    filter_fields=[
        "status",
        "auto_detected",
        "analysis",
    ],
    ordering=[
        "-created_at",
    ],
    select_related=[
        "analysis",
        "triggered_by",
        "reviewed_by",
    ],
    prefetch_related=[
        "causes",
        "logs",
    ],
    queryset_factory=nonconformity_qs,
    inline_edit_fields=[
        "status",
        "corrective_action",
        "preventive_action",
        "root_cause",
    ],
    bulk_actions={
        "close": True,
        "reopen": True,
        "evaluate_risk": True,
    },
)


safe_register(
    Cause,
    search_fields=[
        "name",
        "description",
    ],
    ordering=[
        "name",
    ],
    select_related=[
        "created_by",
    ],
    inline_edit_fields=[
        "name",
        "description",
    ],
)


# ==========================================================
# LOGS
# ==========================================================
safe_register(
    HeavyMetalAnalysisLog,
    search_fields=[
        "action",
        "remarks",
        "analysis__reference_id",
    ],
    filter_fields=[
        "action",
        "auto_generated",
    ],
    ordering=[
        "-created_at",
    ],
    select_related=[
        "analysis",
        "actor",
    ],
    queryset_factory=analysis_log_qs,
)


safe_register(
    HeavyMetalNonConformityLog,
    search_fields=[
        "action",
        "remarks",
        "nonconformity__parameter_name",
    ],
    filter_fields=[
        "action",
        "auto_generated",
    ],
    ordering=[
        "-created_at",
    ],
    select_related=[
        "nonconformity",
        "actor",
    ],
    queryset_factory=nonconformity_log_qs,
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[heavy_metal.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[heavy_metal.registry] registry unavailable during import"
    )