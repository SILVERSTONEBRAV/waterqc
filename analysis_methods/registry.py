# analysis_methods/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "analysis_methods"


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
ChemicalAnalysisMethod = get_model("ChemicalAnalysisMethod")
MicrobialMethod = get_model("MicrobialMethod")
WWAnalysisMethod = get_model("WWAnalysisMethod")
CWAnalysisMethod = get_model("CWAnalysisMethod")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "ChemicalAnalysisMethod": "flask",
    "MicrobialMethod": "bacteria",
    "WWAnalysisMethod": "droplet",
    "CWAnalysisMethod": "glass-water",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "ChemicalAnalysisMethod": "analysis_methods",
    "MicrobialMethod": "analysis_methods",
    "WWAnalysisMethod": "analysis_methods",
    "CWAnalysisMethod": "analysis_methods",
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
        "verbose_name": str(model._meta.verbose_name or verbose),
        "verbose_name_plural": str(
            model._meta.verbose_name_plural or f"{verbose}s"
        ),
    }


# ==========================================================
# QUERYSET FACTORIES
# ==========================================================
def method_qs(model) -> QuerySet:
    return model.objects.select_related(
        "created_by",
        "updated_by",
    )


# ==========================================================
# SHARED CONFIG
# ==========================================================
BASE_METHOD_CONFIG = {
    "filter_fields": [
        "is_active",
        "version",
    ],
    "ordering": [
        "-updated_at",
    ],
    "select_related": [
        "created_by",
        "updated_by",
    ],
    "queryset_factory": method_qs,
    "bulk_actions": {
        "activate": True,
        "deactivate": True,
    },
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
            "[analysis_methods.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# CHEMICAL ANALYSIS METHOD
# ==========================================================
chemical_config = BASE_METHOD_CONFIG.copy()

chemical_config.update(
    {
        "search_fields": [
            "method",
            "kebs_reference",
            "description",
            "category",
        ],
        "filter_fields": [
            "is_active",
            "version",
            "rounding_mode",
            "category",
            "unit",
        ],
        "inline_edit_fields": [
            "method",
            "kebs_reference",
            "unit",
            "rounding_precision",
            "rounding_mode",
            "category",
            "is_active",
        ],
    }
)

safe_register(
    ChemicalAnalysisMethod,
    **chemical_config,
)


# ==========================================================
# MICROBIAL METHOD
# ==========================================================
microbial_config = BASE_METHOD_CONFIG.copy()

microbial_config.update(
    {
        "search_fields": [
            "name",
            "kebs_reference",
            "description",
            "confirmatory_tests",
        ],
        "filter_fields": [
            "status",
            "is_active",
            "version",
        ],
        "inline_edit_fields": [
            "name",
            "kebs_reference",
            "status",
            "is_active",
        ],
    }
)

safe_register(
    MicrobialMethod,
    **microbial_config,
)


# ==========================================================
# WASTE WATER ANALYSIS METHOD
# ==========================================================
ww_config = BASE_METHOD_CONFIG.copy()

ww_config.update(
    {
        "search_fields": [
            "name",
            "reference",
        ],
        "inline_edit_fields": [
            "name",
            "reference",
            "is_active",
        ],
    }
)

safe_register(
    WWAnalysisMethod,
    **ww_config,
)


# ==========================================================
# CLEAN WATER ANALYSIS METHOD
# ==========================================================
cw_config = BASE_METHOD_CONFIG.copy()

cw_config.update(
    {
        "search_fields": [
            "name",
            "reference",
        ],
        "inline_edit_fields": [
            "name",
            "reference",
            "is_active",
        ],
    }
)

safe_register(
    CWAnalysisMethod,
    **cw_config,
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[analysis_methods.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[analysis_methods.registry] registry unavailable during import"
    )