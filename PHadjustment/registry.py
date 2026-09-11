# PHadjustment/registry.py

from __future__ import annotations

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "PHadjustment"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================
def get_model(name: str):
    """
    Lazy model resolver.

    Prevents circular imports during Django app loading.
    """
    return apps.get_model(APP_LABEL, name)


# ==========================================================
# MODEL REFERENCES
# ==========================================================
PHAdjustmentTest = get_model("PHAdjustmentTest")
PHAdjustmentJarResult = get_model("PHAdjustmentJarResult")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "PHAdjustmentTest": "flask",
    "PHAdjustmentJarResult": "vials",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "PHAdjustmentTest": "laboratory",
    "PHAdjustmentJarResult": "laboratory",
}


# ==========================================================
# DISPLAY HELPERS
# ==========================================================
def humanize_model_name(model) -> str:
    """
    Convert CamelCase model names into readable labels.

    Example:
        PHAdjustmentJarResult
        ->
        PH Adjustment Jar Result
    """
    return re.sub(
        r"(?<!^)(?=[A-Z])",
        " ",
        model.__name__,
    ).strip()


def build_meta(model) -> Dict[str, Any]:
    """
    Build registry metadata shared by all models.
    """
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
def ph_adjustment_test_qs(model) -> QuerySet:
    """
    Optimized queryset for PHAdjustmentTest.
    """
    return (
        model.objects
        .select_related(
            "treatment_plant",
            "source_jar",
            "analyst",
            "verified_by",
            "confirmed_by",
            "approved_by",
        )
        .prefetch_related(
            "results",
        )
    )


def ph_adjustment_result_qs(model) -> QuerySet:
    """
    Optimized queryset for PHAdjustmentJarResult.
    """
    return (
        model.objects
        .select_related(
            "test",
            "test__treatment_plant",
            "test__source_jar",
        )
    )
# ==========================================================
# REGISTRATION WRAPPER
# ==========================================================
def safe_register(model, **kwargs):
    """
    Registry normalization layer.

    Adds consistent metadata and UI configuration before
    delegating to the core registry.
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

    # remove unsupported keys if present
    kwargs.pop("templates", None)

    try:
        return register_model(**kwargs)(model)

    except Exception:
        logger.exception(
            "[PHadjustment.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# PH ADJUSTMENT TEST
# ==========================================================
safe_register(
    PHAdjustmentTest,
    search_fields=[
        "treatment_plant__name",
        "remarks",
    ],
    filter_fields=[
        "treatment_plant",
        "test_date",
        "analyst",
        "verified_by",
        "confirmed_by",
        "approved_by",
        "needs_review",
    ],
    ordering=[
        "-test_date",
    ],
    select_related=[
        "treatment_plant",
        "source_jar",
        "analyst",
        "verified_by",
        "confirmed_by",
        "approved_by",
    ],
    prefetch_related=[
        "results",
    ],
    queryset_factory=ph_adjustment_test_qs,
    inline_edit_fields=[
        "remarks",
        "analyst",
        "established_dosage_ml",
    ],
    bulk_actions={
        "verify": True,
        "confirm": True,
        "approve": True,
        "revert_verification": True,
        "revert_confirmation": True,
        "revert_approval": True,
    },
)
# ==========================================================
# PH ADJUSTMENT JAR RESULT
# ==========================================================
safe_register(
    PHAdjustmentJarResult,
    search_fields=[
        "test__treatment_plant__name",
        "test__analyst__username",
    ],
    filter_fields=[
        "test",
        "is_optimal",
        "performance_rank",
    ],
    ordering=[
        "performance_rank",
        "jar_number",
    ],
    select_related=[
        "test",
        "test__treatment_plant",
        "test__source_jar",
        "test__analyst",
    ],
    queryset_factory=ph_adjustment_result_qs,
    inline_edit_fields=[
        "resulting_ph",
        "performance_rank",
        "is_optimal",
    ],
    bulk_actions={
        "mark_optimal": True,
        "clear_ranking": True,
    },
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[PHadjustment.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[PHadjustment.registry] registry unavailable during import"
    )