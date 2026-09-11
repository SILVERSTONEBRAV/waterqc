# jartest/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "jartest"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================
def get_model(name: str):
    """
    Lazy model resolver.
    Prevents circular import issues.
    """
    return apps.get_model(APP_LABEL, name)


# ==========================================================
# MODEL REFERENCES
# ==========================================================
RawWater = get_model("RawWater")
RawWaterAnalysis = get_model("RawWaterAnalysis")

JarTest = get_model("JarTest")
JarResult = get_model("JarResult")
JarMeasurement = get_model("JarMeasurement")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "RawWater": "water",
    "RawWaterAnalysis": "flask",

    "JarTest": "vial-circle-check",
    "JarResult": "beaker",
    "JarMeasurement": "microscope",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "RawWater": "raw-water",
    "RawWaterAnalysis": "raw-water",

    "JarTest": "jar-tests",
    "JarResult": "jar-tests",
    "JarMeasurement": "jar-tests",
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
def raw_water_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "treatment_plant",
            "coagulant",
        )
        .prefetch_related(
            "analyses",
            "jar_tests",
        )
    )


def raw_water_analysis_qs(model) -> QuerySet:
    return model.objects.select_related(
        "raw_water",
        "parameter",
        "parameter__parameter",
    )


def jar_test_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "treatment_plant",
            "raw_water",
            "coagulant",
            "analyst",
            "verified_by",
            "confirmed_by",
            "approved_by",
        )
        .prefetch_related(
            "jar_results",
            "jar_results__measurements",
        )
    )


def jar_result_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "jar_test",
        )
        .prefetch_related(
            "measurements",
            "measurements__parameter",
            "measurements__parameter__parameter",
        )
    )


def jar_measurement_qs(model) -> QuerySet:
    return model.objects.select_related(
        "jar_result",
        "parameter",
        "parameter__parameter",
    )


# ==========================================================
# REGISTRATION WRAPPER
# ==========================================================
def safe_register(model, **kwargs):
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
            "[jartest.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# RAW WATER
# ==========================================================
safe_register(
    RawWater,
    search_fields=[
        "treatment_plant__name",
        "source_name",
        "location_description",
        "coagulant__name",
    ],
    filter_fields=[
        "treatment_plant",
        "coagulant",
        "sampled_at",
    ],
    ordering=[
        "-sampled_at",
    ],
    select_related=[
        "treatment_plant",
        "coagulant",
    ],
    prefetch_related=[
        "analyses",
        "jar_tests",
    ],
    queryset_factory=raw_water_qs,
    inline_edit_fields=[
        "source_name",
        "location_description",
        "coagulant",
        "coagulant_concentration_ppm",
        "remarks",
    ],
)


# ==========================================================
# RAW WATER ANALYSIS
# ==========================================================
safe_register(
    RawWaterAnalysis,
    search_fields=[
        "raw_water__source_name",
        "parameter__parameter__name",
    ],
    filter_fields=[
        "raw_water",
        "parameter",
    ],
    ordering=[
        "parameter__parameter__name",
    ],
    select_related=[
        "raw_water",
        "parameter",
        "parameter__parameter",
    ],
    queryset_factory=raw_water_analysis_qs,
    inline_edit_fields=[
        "parameter",
        "value",
    ],
)


# ==========================================================
# JAR TEST
# ==========================================================
safe_register(
    JarTest,
    search_fields=[
        "treatment_plant__name",
        "coagulant__name",
        "remarks",
    ],
    filter_fields=[
        "treatment_plant",
        "coagulant",
        "analyst",
        "needs_review",
        "test_date",
    ],
    ordering=[
        "-test_date",
    ],
    select_related=[
        "treatment_plant",
        "raw_water",
        "coagulant",
        "analyst",
        "verified_by",
        "confirmed_by",
        "approved_by",
    ],
    prefetch_related=[
        "jar_results",
        "jar_results__measurements",
    ],
    queryset_factory=jar_test_qs,
    inline_edit_fields=[
        "coagulant",
        "established_dosage_mg_per_l",
        "remarks",
        "analyst",
    ],
    bulk_actions={
        "verify": True,
        "confirm": True,
        "approve": True,
        "rank_results": True,
    },
)


# ==========================================================
# JAR RESULT
# ==========================================================
safe_register(
    JarResult,
    search_fields=[
        "jar_test__treatment_plant__name",
    ],
    filter_fields=[
        "jar_test",
        "jar_number",
        "is_optimal",
    ],
    ordering=[
        "performance_rank",
        "jar_number",
    ],
    select_related=[
        "jar_test",
    ],
    prefetch_related=[
        "measurements",
    ],
    queryset_factory=jar_result_qs,
    inline_edit_fields=[
        "dosage_mg_per_l",
        "floc_observation_time",
        "is_optimal",
        "performance_rank",
    ],
)


# ==========================================================
# JAR MEASUREMENT
# ==========================================================
safe_register(
    JarMeasurement,
    search_fields=[
        "parameter__parameter__name",
        "jar_result__jar_test__treatment_plant__name",
    ],
    filter_fields=[
        "jar_result",
        "parameter",
    ],
    ordering=[
        "parameter__parameter__name",
    ],
    select_related=[
        "jar_result",
        "parameter",
        "parameter__parameter",
    ],
    queryset_factory=jar_measurement_qs,
    inline_edit_fields=[
        "parameter",
        "value",
    ],
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[jartest.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[jartest.registry] registry unavailable during import"
    )