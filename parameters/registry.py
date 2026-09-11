# parameters/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "parameters"


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
PhysicochemicalParameter = get_model("PhysicochemicalParameter")
MicrobialParameter = get_model("MicrobialParameter")
HeavyMetalParameter = get_model("HeavyMetalParameter")

WWQParameter_qad = get_model("WWQParameter_qad")
CWQParameter_qad = get_model("CWQParameter_qad")
DistributionParameter_qad = get_model("DistributionParameter_qad")
GigiriParameter_qad = get_model("GigiriParameter_qad")
KabeteParameter_qad = get_model("KabeteParameter_qad")
MicrobialParameter_qad = get_model("MicrobialParameter_qad")

CatchmentParameter_qad = get_model("CatchmentParameter_qad")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "PhysicochemicalParameter": "flask",
    "MicrobialParameter": "bacteria",
    "HeavyMetalParameter": "atom",

    "WWQParameter_qad": "industry",
    "CWQParameter_qad": "water",
    "DistributionParameter_qad": "network-wired",
    "GigiriParameter_qad": "city",
    "KabeteParameter_qad": "shield-check",
    "MicrobialParameter_qad": "virus",

    "CatchmentParameter_qad": "mountain",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "PhysicochemicalParameter": "base_parameters",
    "MicrobialParameter": "base_parameters",
    "HeavyMetalParameter": "base_parameters",

    "WWQParameter_qad": "regulatory_nema",
    "CWQParameter_qad": "regulatory_kebs",
    "DistributionParameter_qad": "regulatory_kebs",
    "GigiriParameter_qad": "regulatory_internal",
    "KabeteParameter_qad": "regulatory_internal",
    "MicrobialParameter_qad": "regulatory_microbiology",

    "CatchmentParameter_qad": "catchment",
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
def base_param_qs(model) -> QuerySet:
    return model.objects.all().order_by("name")


def standard_param_qs(model) -> QuerySet:
    return model.objects.all().order_by("name")


# ==========================================================
# SHARED CONFIGS
# ==========================================================
BASE_CONFIG = {
    "search_fields": [
        "name",
        "unit",
    ],
    "filter_fields": [
        "unit",
        "is_active",
    ],
    "ordering": ["name"],
}

STANDARD_CONFIG = {
    "search_fields": [
        "name",
        "unit",
    ],
    "filter_fields": [
        "unit",
        "is_active",
    ],
    "ordering": ["name"],
    "inline_edit_fields": [
        "min_standard",
        "max_standard",
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
        GROUPS.get(model.__name__, "parameters"),
    )

    kwargs["ui"] = ui

    kwargs.pop("templates", None)

    try:
        return register_model(**kwargs)(model)
    except Exception:
        logger.exception(
            "[parameters.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# BASE PARAMETERS
# ==========================================================
safe_register(
    PhysicochemicalParameter,
    **BASE_CONFIG,
    queryset_factory=base_param_qs,
)

safe_register(
    MicrobialParameter,
    **BASE_CONFIG,
    queryset_factory=base_param_qs,
)

safe_register(
    HeavyMetalParameter,
    **BASE_CONFIG,
    queryset_factory=base_param_qs,
)


# ==========================================================
# REGULATORY PARAMETERS (STANDARDIZED)
# ==========================================================
safe_register(
    WWQParameter_qad,
    **STANDARD_CONFIG,
    queryset_factory=standard_param_qs,
)

safe_register(
    CWQParameter_qad,
    **STANDARD_CONFIG,
    queryset_factory=standard_param_qs,
)

safe_register(
    DistributionParameter_qad,
    **STANDARD_CONFIG,
    queryset_factory=standard_param_qs,
)

safe_register(
    GigiriParameter_qad,
    **STANDARD_CONFIG,
    queryset_factory=standard_param_qs,
)

safe_register(
    KabeteParameter_qad,
    **STANDARD_CONFIG,
    queryset_factory=standard_param_qs,
)

safe_register(
    MicrobialParameter_qad,
    **STANDARD_CONFIG,
    queryset_factory=standard_param_qs,
)


# ==========================================================
# CATCHMENT PARAMETERS
# ==========================================================
safe_register(
    CatchmentParameter_qad,
    **BASE_CONFIG,
    queryset_factory=base_param_qs,
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[parameters.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[parameters.registry] registry unavailable during import"
    )