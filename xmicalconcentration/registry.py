import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "xmicalconcentration"


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
XmicalConcentration = get_model("XmicalConcentration")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "XmicalConcentration": "vial",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "XmicalConcentration": "chemical_analysis",
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
def xmical_concentration_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "phase",
        "chemical",
        "tank",
        "measured_by",
        "created_by",
        "updated_by",
    )


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
    ui.setdefault("icon", ICONS.get(model.__name__, "flask"))
    ui.setdefault("group", GROUPS.get(model.__name__, "general"))

    kwargs["ui"] = ui

    kwargs.pop("templates", None)

    try:
        return register_model(**kwargs)(model)
    except Exception:
        logger.exception(
            "[xmicalconcentration.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# REGISTRATION
# ==========================================================
safe_register(
    XmicalConcentration,
    search_fields=[
        "chemical_name",
        "treatment_plant__name",
        "tank__name",
    ],
    filter_fields=[
        "treatment_plant",
        "phase",
        "chemical",
        "tank",
        "measured_by",
    ],
    ordering=["-measurement_date"],
    select_related=[
        "treatment_plant",
        "phase",
        "chemical",
        "tank",
        "measured_by",
        "created_by",
        "updated_by",
    ],
    queryset_factory=xmical_concentration_qs,
    inline_edit_fields=[
        "hydrometer_reading",
        "concentration_mg_per_l",
        "comments",
    ],
    bulk_actions={
        "delete_selected": True,
        "export_selected": True,
    },
)

# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[xmicalconcentration.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[xmicalconcentration.registry] registry unavailable during import"
    )