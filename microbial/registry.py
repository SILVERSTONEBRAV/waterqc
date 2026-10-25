import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "microbial"


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
MicrobialSamplingSchedule = get_model("MicrobialSamplingSchedule")
MicrobialSamplingTime = get_model("MicrobialSamplingTime")

MicrobialAnalysis = get_model("MicrobialAnalysis")

MicrobialParameterResult = get_model("MicrobialParameterResult")
TreatedWaterParameterResult = get_model("TreatedWaterParameterResult")

MicrobialNonConformity = get_model("MicrobialNonConformity")

MicrobialAnalysisLog = get_model("MicrobialAnalysisLog")
MicrobialNonConformityLog = get_model("MicrobialNonConformityLog")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "MicrobialSamplingSchedule": "clock",
    "MicrobialSamplingTime": "calendar-clock",

    "MicrobialAnalysis": "microscope",

    "MicrobialParameterResult": "vial",
    "TreatedWaterParameterResult": "water",

    "MicrobialNonConformity": "triangle-exclamation",

    "MicrobialAnalysisLog": "file-lines",
    "MicrobialNonConformityLog": "clipboard-list",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "MicrobialSamplingSchedule": "sampling",
    "MicrobialSamplingTime": "sampling",

    "MicrobialAnalysis": "analysis",

    "MicrobialParameterResult": "results",
    "TreatedWaterParameterResult": "results",

    "MicrobialNonConformity": "compliance",

    "MicrobialAnalysisLog": "logs",
    "MicrobialNonConformityLog": "logs",
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
# QUERYSET FACTORIES
# ==========================================================
def schedule_qs(model) -> QuerySet:
    return model.objects.prefetch_related("times")


def time_qs(model) -> QuerySet:
    return model.objects.select_related("schedule")


def analysis_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "treatment_plant_phase",
        "method",
        "shift",
        "sampling_time",
        "analysed_by",
        "verified_by",
        "approved_by",
    ).prefetch_related("logs", "nonconformities")


def microbial_result_qs(model) -> QuerySet:
    return model.objects.select_related(
        "analysis",
        "parameter",
    )


def treated_result_qs(model) -> QuerySet:
    return model.objects.select_related(
        "analysis",
        "parameter",
    )


def nc_qs(model) -> QuerySet:
    return model.objects.select_related(
        "analysis",
        "triggered_by",
    ).prefetch_related("logs")


def analysis_log_qs(model) -> QuerySet:
    return model.objects.select_related(
        "analysis",
        "actor",
    )


def nc_log_qs(model) -> QuerySet:
    return model.objects.select_related(
        "nonconformity",
        "actor",
    )


# ==========================================================
# SHARED REGISTRY WRAPPER
# ==========================================================
def safe_register(model, **kwargs):
    """
    Registry normalization layer (consistent with ca/sc pattern)
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
            "[microbial.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# SAMPLING
# ==========================================================
safe_register(
    MicrobialSamplingSchedule,
    search_fields=["start_time"],
    filter_fields=["enabled"],
    ordering=["start_time"],
    queryset_factory=schedule_qs,
    inline_edit_fields=["start_time", "interval_minutes", "enabled"],
)

safe_register(
    MicrobialSamplingTime,
    search_fields=["time"],
    filter_fields=["schedule"],
    ordering=["time"],
    queryset_factory=time_qs,
    select_related=["schedule"],
)


# ==========================================================
# ANALYSIS CORE
# ==========================================================
safe_register(
    MicrobialAnalysis,
    search_fields=["reference_id", "treatment_plant__name"],
    filter_fields=["state", "analysis_date", "shift"],
    ordering=["analysis_date"],
    queryset_factory=analysis_qs,
    select_related=[
        "treatment_plant",
        "treatment_plant_phase",
        "method",
        "shift",
        "sampling_time",
    ],
    inline_edit_fields=[
        "state",
        "analysis_date",
    ],
    bulk_actions={
        "verify": True,
        "confirm": True,
        "approve": True,
    },
)


# ==========================================================
# RESULTS
# ==========================================================
safe_register(
    MicrobialParameterResult,
    search_fields=["parameter__parameter__name"],
    filter_fields=["analysis"],
    ordering=["analysis"],
    queryset_factory=microbial_result_qs,
    select_related=["analysis", "parameter"],
    inline_edit_fields=["value", "entry_status"],
)

safe_register(
    TreatedWaterParameterResult,
    search_fields=["parameter__parameter__name"],
    filter_fields=["analysis"],
    ordering=["analysis"],
    queryset_factory=treated_result_qs,
    select_related=["analysis", "parameter"],
)


# ==========================================================
# NONCONFORMITIES
# ==========================================================
safe_register(
    MicrobialNonConformity,
    search_fields=["parameter_name"],
    filter_fields=["status", "analysis"],
    ordering=["-created_at"],
    queryset_factory=nc_qs,
    select_related=["analysis", "triggered_by"],
    inline_edit_fields=[
        "status",
        "risk_score",
        "escalation_level",
    ],
    bulk_actions={
        "close": True,
        "escalate": True,
    },
)


# ==========================================================
# LOGS
# ==========================================================
safe_register(
    MicrobialAnalysisLog,
    search_fields=["action", "analysis__reference_id"],
    filter_fields=["analysis"],
    ordering=["-created_at"],
    queryset_factory=analysis_log_qs,
    select_related=["analysis", "actor"],
)

safe_register(
    MicrobialNonConformityLog,
    search_fields=["action", "nonconformity__parameter_name"],
    filter_fields=["nonconformity"],
    ordering=["-created_at"],
    queryset_factory=nc_log_qs,
    select_related=["nonconformity", "actor"],
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[microbial.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[microbial.registry] registry unavailable during import"
    )
