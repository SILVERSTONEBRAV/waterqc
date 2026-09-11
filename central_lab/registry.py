import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "central_lab"


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
KabeteSamplingPoint = get_model("KabeteSamplingPoint")
GigiriSamplingPoint = get_model("GigiriSamplingPoint")
SampleCategory = get_model("SampleCategory")

RegionSample = get_model("RegionSample")
FCASample = get_model("FCASample")
CatchmentSample = get_model("CatchmentSample")
KabeteSample = get_model("KabeteSample")
GigiriSample = get_model("GigiriSample")

RegionSampleAnalysis = get_model("RegionSampleAnalysis")
FCASampleAnalysis = get_model("FCASampleAnalysis")
CatchmentSampleAnalysis = get_model("CatchmentSampleAnalysis")
KabeteSampleAnalysis = get_model("KabeteSampleAnalysis")
GigiriSampleAnalysis = get_model("GigiriSampleAnalysis")

RegionSampleParameterResult = get_model("RegionSampleParameterResult")
FCASampleParameterResult = get_model("FCASampleParameterResult")
CatchmentSampleParameterResult = get_model("CatchmentSampleParameterResult")
KabeteSampleParameterResult = get_model("KabeteSampleParameterResult")
GigiriSampleParameterResult = get_model("GigiriSampleParameterResult")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "KabeteSamplingPoint": "location-dot",
    "GigiriSamplingPoint": "location-dot",

    "SampleCategory": "tags",

    "RegionSample": "vial",
    "FCASample": "vial",
    "CatchmentSample": "vial",
    "KabeteSample": "vial",
    "GigiriSample": "vial",

    "RegionSampleAnalysis": "flask",
    "FCASampleAnalysis": "flask",
    "CatchmentSampleAnalysis": "flask",
    "KabeteSampleAnalysis": "flask",
    "GigiriSampleAnalysis": "flask",

    "RegionSampleParameterResult": "chart-line",
    "FCASampleParameterResult": "chart-line",
    "CatchmentSampleParameterResult": "chart-line",
    "KabeteSampleParameterResult": "chart-line",
    "GigiriSampleParameterResult": "chart-line",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "KabeteSamplingPoint": "sampling",
    "GigiriSamplingPoint": "sampling",

    "SampleCategory": "configuration",

    "RegionSample": "samples",
    "FCASample": "samples",
    "CatchmentSample": "samples",
    "KabeteSample": "samples",
    "GigiriSample": "samples",

    "RegionSampleAnalysis": "analysis",
    "FCASampleAnalysis": "analysis",
    "CatchmentSampleAnalysis": "analysis",
    "KabeteSampleAnalysis": "analysis",
    "GigiriSampleAnalysis": "analysis",

    "RegionSampleParameterResult": "results",
    "FCASampleParameterResult": "results",
    "CatchmentSampleParameterResult": "results",
    "KabeteSampleParameterResult": "results",
    "GigiriSampleParameterResult": "results",
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
def sampling_point_qs(model) -> QuerySet:
    return model.objects.all()


def sample_qs(model) -> QuerySet:
    return model.objects.select_related(
        "sampling_point",
    )


def analysis_qs(model) -> QuerySet:
    return model.objects.select_related(
        "sample",
        "analysed_by",
        "verified_by",
        "confirmed_by",
        "approved_by",
    )


def parameter_result_qs(model) -> QuerySet:
    return model.objects.select_related(
        "analysis",
        "parameter",
        "analysis_method",
    )


# ==========================================================
# SHARED CONFIG
# ==========================================================
RESULT_CONFIG = {
    "search_fields": [
        "parameter__name",
    ],
    "ordering": [
        "parameter",
    ],
    "queryset_factory": parameter_result_qs,
}


ANALYSIS_CONFIG = {
    "search_fields": [
        "sample__reference_id",
        "remarks",
    ],
    "filter_fields": [
        "status",
    ],
    "ordering": [
        "-analysis_datetime",
    ],
    "queryset_factory": analysis_qs,
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
        GROUPS.get(model.__name__, "general"),
    )

    kwargs["ui"] = ui

    kwargs.pop("templates", None)

    try:
        return register_model(**kwargs)(model)
    except Exception:
        logger.exception(
            "[central_lab.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# SAMPLING POINTS
# ==========================================================
safe_register(
    KabeteSamplingPoint,
    search_fields=["name"],
    ordering=["name"],
    queryset_factory=sampling_point_qs,
    inline_edit_fields=[
        "name",
        "description",
    ],
)

safe_register(
    GigiriSamplingPoint,
    search_fields=["name"],
    ordering=["name"],
    queryset_factory=sampling_point_qs,
    inline_edit_fields=[
        "name",
        "description",
    ],
)


# ==========================================================
# SAMPLE CATEGORY
# ==========================================================
safe_register(
    SampleCategory,
    search_fields=["name"],
    ordering=["name"],
    filter_fields=["is_active"],
    inline_edit_fields=[
        "name",
        "is_active",
    ],
)


# ==========================================================
# SAMPLE FACTORY
# ==========================================================
def register_sample(model):
    safe_register(
        model,
        search_fields=[
            "reference_id",
            "barcode",
        ],
        ordering=[
            "-sampling_date",
            "-sampling_time",
        ],
        queryset_factory=sample_qs,
        inline_edit_fields=[
            "sampling_date",
            "sampling_time",
            "remarks",
        ],
    )


register_sample(RegionSample)
register_sample(FCASample)
register_sample(CatchmentSample)
register_sample(KabeteSample)
register_sample(GigiriSample)


# ==========================================================
# ANALYSIS FACTORY
# ==========================================================
def register_analysis(model):
    safe_register(
        model,
        **ANALYSIS_CONFIG,
        inline_edit_fields=[
            "status",
            "remarks",
        ],
    )


register_analysis(RegionSampleAnalysis)
register_analysis(FCASampleAnalysis)
register_analysis(CatchmentSampleAnalysis)
register_analysis(KabeteSampleAnalysis)
register_analysis(GigiriSampleAnalysis)


# ==========================================================
# RESULT FACTORY
# ==========================================================
def register_result(model):
    safe_register(
        model,
        **RESULT_CONFIG,
        inline_edit_fields=[
            "result",
            "quality_compliance",
        ],
    )


register_result(RegionSampleParameterResult)
register_result(FCASampleParameterResult)
register_result(CatchmentSampleParameterResult)
register_result(KabeteSampleParameterResult)
register_result(GigiriSampleParameterResult)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[central_lab.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[central_lab.registry] registry unavailable during import"
    )