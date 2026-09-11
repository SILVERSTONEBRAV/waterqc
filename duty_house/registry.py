# duty_house/registry.py

import logging
import re
from typing import Any, Dict, Optional, List

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "duty_house"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================
def get_model(name: str):
    try:
        return apps.get_model(APP_LABEL, name)
    except LookupError:
        logger.exception(
            "[duty_house.registry] Failed resolving model %s",
            name,
        )
        return None


Location = get_model("Location")
DutyHouse = get_model("DutyHouse")
DutyHouseUnit = get_model("DutyHouseUnit")
DutyHouseOccupancy = get_model("DutyHouseOccupancy")
OccupancyTransfer = get_model("OccupancyTransfer")


# ==========================================================
# UI CONFIG: GLOBAL HIDDEN FIELDS (IMPORTANT)
# ==========================================================
GLOBAL_HIDDEN_FIELDS = {
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
}


# ==========================================================
# GROUPS
# ==========================================================
GROUPS = {
    "Location": "configuration",
    "DutyHouse": "housing",
    "DutyHouseUnit": "housing",
    "DutyHouseOccupancy": "occupancy",
    "OccupancyTransfer": "occupancy",
}


# ==========================================================
# ICONS
# ==========================================================
ICONS = {
    "Location": "location-dot",
    "DutyHouse": "house",
    "DutyHouseUnit": "door-open",
    "DutyHouseOccupancy": "bed",
    "OccupancyTransfer": "right-left",
}


# ==========================================================
# HELPERS
# ==========================================================
def humanize_model_name(model) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", model.__name__).strip()


def build_meta(model) -> Dict[str, Any]:
    verbose = (
        getattr(model._meta, "verbose_name", None)
        or humanize_model_name(model)
    )

    return {
        "key": f"{model._meta.app_label}.{model._meta.model_name}",
        "app_label": model._meta.app_label,
        "model_name": model._meta.model_name,
        "verbose_name": verbose.title(),
        "verbose_name_plural": getattr(
            model._meta,
            "verbose_name_plural",
            f"{verbose}s",
        ),
    }


# ==========================================================
# QUERYSET STRATEGY
# ==========================================================
def location_qs(model):
    return model.objects.select_related(
        "plant",
        "created_by",
        "updated_by",
    ).prefetch_related("duty_houses")


def house_qs(model):
    return model.objects.select_related(
        "plant",
        "location",
        "created_by",
        "updated_by",
    ).prefetch_related("units", "occupancies")


def unit_qs(model):
    return model.objects.select_related(
        "duty_house",
        "created_by",
        "updated_by",
    ).prefetch_related("occupancies")


def occupancy_qs(model):
    return model.objects.select_related(
        "duty_house",
        "unit",
        "user",
        "check_in_by",
        "check_out_by",
        "created_by",
        "updated_by",
    )


def transfer_qs(model):
    return model.objects.select_related(
        "from_unit",
        "to_unit",
        "user",
        "transferred_by",
        "created_by",
        "updated_by",
    )


# ==========================================================
# REGISTRY WRAPPER (ENHANCED WITH FIELD HIDING)
# ==========================================================
def safe_register(
    model,
    *,
    search_fields=None,
    filter_fields=None,
    ordering=None,
    inline_edit_fields=None,
    select_related=None,
    prefetch_related=None,
    queryset_factory=None,
    bulk_actions=None,
    permissions=None,
    hidden_fields=None,   # 👈 NEW
    meta=None,
    ui=None,
):
    if model is None:
        logger.warning(
            "[duty_house.registry] skipped null model"
        )
        return

    name = model.__name__

    meta = meta or {}
    meta.update(build_meta(model))

    ui = ui or {}
    ui.setdefault("icon", ICONS.get(name, "cube"))
    ui.setdefault("group", GROUPS.get(name, "general"))

    # ======================================================
    # CRITICAL: FIELD HIDING LOGIC
    # ======================================================
    hidden_fields = set(hidden_fields or [])
    hidden_fields |= GLOBAL_HIDDEN_FIELDS

    def filter_fields_list(fields):
        return [
            f for f in (fields or [])
            if f not in hidden_fields
        ]

    search_fields = filter_fields_list(search_fields)
    filter_fields = filter_fields_list(filter_fields)
    ordering = filter_fields_list(ordering)
    inline_edit_fields = filter_fields_list(inline_edit_fields)

    try:
        register_model(
            search_fields=search_fields,
            filter_fields=filter_fields,
            ordering=ordering,
            inline_edit_fields=inline_edit_fields,
            select_related=select_related or [],
            prefetch_related=prefetch_related or [],
            queryset_factory=queryset_factory,
            bulk_actions=bulk_actions or {},
            permissions=permissions or {},
            meta=meta,
            ui=ui,
        )(model)

    except Exception:
        logger.exception(
            "[duty_house.registry] failed registering %s",
            name,
        )


# ==========================================================
# LOCATION
# ==========================================================
safe_register(
    Location,
    search_fields=["name", "code", "plant__name"],
    filter_fields=["plant", "location_type", "is_active"],
    ordering=["plant__name", "name"],
    select_related=["plant"],
    prefetch_related=["duty_houses"],
    queryset_factory=location_qs,
    inline_edit_fields=[
        "name",
        "code",
        "location_type",
        "is_active",
        # created_by / updated_by automatically hidden
    ],
)


# ==========================================================
# DUTY HOUSE
# ==========================================================
safe_register(
    DutyHouse,
    search_fields=[
        "house_number",
        "name",
        "location__name",
        "plant__name",
    ],
    filter_fields=["plant", "location", "status", "is_active"],
    ordering=["house_number"],
    select_related=["plant", "location"],
    prefetch_related=["units", "occupancies"],
    queryset_factory=house_qs,
    inline_edit_fields=[
        "house_number",
        "name",
        "status",
        "maintenance_score",
        "critical_issues_open",
        "is_active",
    ],
    bulk_actions={
        "activate": True,
        "decommission": True,
        "mark_maintenance": True,
    },
)


# ==========================================================
# UNIT
# ==========================================================
safe_register(
    DutyHouseUnit,
    search_fields=[
        "unit_number",
        "duty_house__house_number",
    ],
    filter_fields=[
        "duty_house",
        "unit_type",
        "status",
        "floor",
    ],
    ordering=[
        "duty_house",
        "floor",
        "unit_number",
    ],
    select_related=["duty_house"],
    prefetch_related=["occupancies"],
    queryset_factory=unit_qs,
    inline_edit_fields=[
        "unit_number",
        "unit_type",
        "floor",
        "status",
        "max_occupants",
    ],
)


# ==========================================================
# OCCUPANCY
# ==========================================================
safe_register(
    DutyHouseOccupancy,
    search_fields=[
        "user__username",
        "unit__unit_number",
        "duty_house__house_number",
    ],
    filter_fields=[
        "status",
        "is_current",
        "duty_house",
        "unit",
    ],
    ordering=["-start_date"],
    select_related=[
        "duty_house",
        "unit",
        "user",
        "check_in_by",
        "check_out_by",
    ],
    queryset_factory=occupancy_qs,
    inline_edit_fields=[
        "status",
        "is_current",
        "end_date",
        "exit_reason",
    ],
)


# ==========================================================
# TRANSFERS
# ==========================================================
safe_register(
    OccupancyTransfer,
    search_fields=[
        "user__username",
        "from_unit__unit_number",
        "to_unit__unit_number",
    ],
    filter_fields=["from_unit", "to_unit", "user"],
    ordering=["-transferred_at"],
    select_related=[
        "from_unit",
        "to_unit",
        "user",
        "transferred_by",
    ],
    queryset_factory=transfer_qs,
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[duty_house.registry] loaded successfully"
    )

except Exception:
    logger.exception(
        "[duty_house.registry] registry unavailable"
    )