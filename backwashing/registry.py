# backwashing/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "backwashing"


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
OperationStatus = get_model("OperationStatus")
PhaseLossRate = get_model("PhaseLossRate")
Backwashing = get_model("Backwashing")
Disludging = get_model("Disludging")
PumpFlush = get_model("PumpFlush")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "OperationStatus": "traffic-light",
    "PhaseLossRate": "gauge",

    "Backwashing": "filter-circle-xmark",
    "Disludging": "arrows-spin",
    "PumpFlush": "faucet-drip",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "OperationStatus": "configuration",
    "PhaseLossRate": "configuration",

    "Backwashing": "operations",
    "Disludging": "operations",
    "PumpFlush": "operations",
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
def status_qs(model) -> QuerySet:
    return model.objects.all()


def phase_loss_qs(model) -> QuerySet:
    return model.objects.select_related(
        "phase",
    )


def backwashing_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "phase",
        "filter_unit",
        "performed_by",
        "shift_assignment",
        "status",
    )


def disludging_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "phase",
        "clarifier",
        "performed_by",
        "shift_assignment",
        "status",
    )


def flush_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "phase",
        "chemical_pump",
        "performed_by",
        "shift_assignment",
        "status",
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
            "[backwashing.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# STATUS
# ==========================================================
safe_register(
    OperationStatus,
    search_fields=["name"],
    ordering=["name"],
    queryset_factory=status_qs,
    inline_edit_fields=[
        "name",
    ],
)


# ==========================================================
# PHASE LOSS RATE
# ==========================================================
safe_register(
    PhaseLossRate,
    search_fields=[
        "phase__name",
        "operation",
    ],
    filter_fields=[
        "phase",
        "operation",
    ],
    ordering=[
        "phase",
        "operation",
    ],
    select_related=[
        "phase",
    ],
    queryset_factory=phase_loss_qs,
    inline_edit_fields=[
        "operation",
        "loss_rate_m3pm",
        "effective_date",
    ],
)


# ==========================================================
# BACKWASHING
# ==========================================================
safe_register(
    Backwashing,
    search_fields=[
        "filter_unit__name",
        "treatment_plant__name",
        "remarks",
    ],
    filter_fields=[
        "treatment_plant",
        "phase",
        "filter_unit",
        "status",
    ],
    ordering=[
        "-start_time",
    ],
    select_related=[
        "treatment_plant",
        "phase",
        "filter_unit",
        "performed_by",
        "shift_assignment",
        "status",
    ],
    queryset_factory=backwashing_qs,
    inline_edit_fields=[
        "status",
        "start_time",
        "end_time",
        "remarks",
    ],
    bulk_actions={
        "mark_completed": True,
        "cancel_selected": True,
    },
)


# ==========================================================
# DISLUDGING
# ==========================================================
safe_register(
    Disludging,
    search_fields=[
        "clarifier__name",
        "treatment_plant__name",
        "remarks",
    ],
    filter_fields=[
        "treatment_plant",
        "phase",
        "clarifier",
        "status",
    ],
    ordering=[
        "-start_time",
    ],
    select_related=[
        "treatment_plant",
        "phase",
        "clarifier",
        "performed_by",
        "shift_assignment",
        "status",
    ],
    queryset_factory=disludging_qs,
    inline_edit_fields=[
        "status",
        "start_time",
        "end_time",
        "remarks",
    ],
    bulk_actions={
        "mark_completed": True,
        "cancel_selected": True,
    },
)


# ==========================================================
# PUMP FLUSH
# ==========================================================
safe_register(
    PumpFlush,
    search_fields=[
        "chemical_pump__name",
        "treatment_plant__name",
        "remarks",
    ],
    filter_fields=[
        "treatment_plant",
        "phase",
        "chemical_pump",
        "status",
    ],
    ordering=[
        "-start_time",
    ],
    select_related=[
        "treatment_plant",
        "phase",
        "chemical_pump",
        "performed_by",
        "shift_assignment",
        "status",
    ],
    queryset_factory=flush_qs,
    inline_edit_fields=[
        "status",
        "start_time",
        "end_time",
        "remarks",
    ],
    bulk_actions={
        "mark_completed": True,
        "cancel_selected": True,
    },
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[backwashing.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[backwashing.registry] registry unavailable during import"
    )