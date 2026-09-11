# chlorinedemand/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "chlorinedemand"


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
ChlorineDemandTest = get_model("ChlorineDemandTest")
ChlorineJarResult = get_model("ChlorineJarResult")


# ==========================================================
# ICONS
# ==========================================================
ICONS = {
    "ChlorineDemandTest": "flask-vial",
    "ChlorineJarResult": "vials",
}


# ==========================================================
# GROUPS
# ==========================================================
GROUPS = {
    "ChlorineDemandTest": "chlorination",
    "ChlorineJarResult": "chlorination",
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
        "verbose_name_plural": str(
            model._meta.verbose_name_plural
        ),
    }


# ==========================================================
# QUERYSET FACTORIES
# ==========================================================
def test_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "treatment_plant",
            "analyst",
            "verified_by",
            "confirmed_by",
            "approved_by",
        )
        .prefetch_related(
            "jar_results",
        )
    )


def jar_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "test",
            "test__treatment_plant",
            "test__analyst",
        )
    )


# ==========================================================
# SHARED REVIEW CONFIG
# ==========================================================
REVIEW_FIELDS = [
    "verified_by",
    "verified_at",
    "confirmed_by",
    "confirmed_at",
    "approved_by",
    "approved_at",
    "needs_review",
]


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
            "[chlorinedemand.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# CHLORINE DEMAND TESTS
# ==========================================================
safe_register(
    ChlorineDemandTest,
    search_fields=[
        "treatment_plant__name",
        "remarks",
        "analyst__username",
        "analyst__first_name",
        "analyst__last_name",
    ],
    filter_fields=[
        "treatment_plant",
        "test_date",
        "analyst",
        "needs_review",
    ],
    ordering=[
        "-test_date",
        "-created_at",
    ],
    select_related=[
        "treatment_plant",
        "analyst",
        "verified_by",
        "confirmed_by",
        "approved_by",
    ],
    prefetch_related=[
        "jar_results",
    ],
    queryset_factory=test_qs,
    inline_edit_fields=[
        "test_date",
        "analyst",
        "remarks",
        "established_dosage_mg_per_l",
    ],
    readonly_fields=[
        "created_at",
        *REVIEW_FIELDS,
    ],
    bulk_actions={
        "verify": True,
        "confirm": True,
        "approve": True,
        "revert_verification": True,
        "revert_confirmation": True,
        "revert_approval": True,
        "rank_results": True,
    },
)


# ==========================================================
# JAR RESULTS
# ==========================================================
safe_register(
    ChlorineJarResult,
    search_fields=[
        "test__treatment_plant__name",
    ],
    filter_fields=[
        "test",
        "jar_number",
        "is_optimal",
        "performance_rank",
    ],
    ordering=[
        "test",
        "performance_rank",
        "jar_number",
    ],
    select_related=[
        "test",
        "test__treatment_plant",
    ],
    queryset_factory=jar_qs,
    inline_edit_fields=[
        "dosage_mg_per_l",
        "residual_chlorine",
    ],
    readonly_fields=[
        "performance_rank",
        "is_optimal",
        "created_at",
    ],
    bulk_actions={
        "recalculate_rank": True,
    },
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[chlorinedemand.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[chlorinedemand.registry] registry unavailable during import"
    )