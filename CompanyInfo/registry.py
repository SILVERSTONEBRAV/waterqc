# CompanyInfo/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "CompanyInfo"


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
CompanyInfo = get_model("CompanyInfo")
RegionalInfo = get_model("RegionalInfo")
ZonalInfo = get_model("ZonalInfo")
SubZonalInfo = get_model("SubZonalInfo")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "CompanyInfo": "building",
    "RegionalInfo": "earth-africa",
    "ZonalInfo": "map",
    "SubZonalInfo": "location-dot",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "CompanyInfo": "organization",
    "RegionalInfo": "geography",
    "ZonalInfo": "geography",
    "SubZonalInfo": "geography",
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
def company_qs(model) -> QuerySet:
    return model.objects.prefetch_related(
        "regions",
    )


def region_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "company",
        )
        .prefetch_related(
            "zones",
        )
    )


def zone_qs(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "region",
            "region__company",
        )
        .prefetch_related(
            "sub_zones",
        )
    )


def subzone_qs(model) -> QuerySet:
    return model.objects.select_related(
        "zone",
        "zone__region",
        "zone__region__company",
    )


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
            "[CompanyInfo.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# COMPANY
# ==========================================================
safe_register(
    CompanyInfo,
    search_fields=[
        "name",
        "address",
        "location",
        "phone_number",
        "telephone",
        "motto",
    ],
    ordering=[
        "name",
    ],
    prefetch_related=[
        "regions",
    ],
    queryset_factory=company_qs,
    inline_edit_fields=[
        "name",
        "address",
        "location",
        "phone_number",
        "telephone",
        "motto",
    ],
)


# ==========================================================
# REGIONS
# ==========================================================
safe_register(
    RegionalInfo,
    search_fields=[
        "name",
        "address",
        "office_location",
        "telephone_number",
    ],
    filter_fields=[
        "company",
    ],
    ordering=[
        "name",
    ],
    select_related=[
        "company",
    ],
    prefetch_related=[
        "zones",
    ],
    queryset_factory=region_qs,
    inline_edit_fields=[
        "name",
        "address",
        "office_location",
        "telephone_number",
    ],
)


# ==========================================================
# ZONES
# ==========================================================
safe_register(
    ZonalInfo,
    search_fields=[
        "name",
        "address",
        "region__name",
        "region__company__name",
    ],
    filter_fields=[
        "region",
    ],
    ordering=[
        "name",
    ],
    select_related=[
        "region",
        "region__company",
    ],
    prefetch_related=[
        "sub_zones",
    ],
    queryset_factory=zone_qs,
    inline_edit_fields=[
        "name",
        "address",
    ],
)


# ==========================================================
# SUB ZONES
# ==========================================================
safe_register(
    SubZonalInfo,
    search_fields=[
        "name",
        "address",
        "zone__name",
        "zone__region__name",
    ],
    filter_fields=[
        "zone",
    ],
    ordering=[
        "name",
    ],
    select_related=[
        "zone",
        "zone__region",
        "zone__region__company",
    ],
    queryset_factory=subzone_qs,
    inline_edit_fields=[
        "name",
        "address",
    ],
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[CompanyInfo.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[CompanyInfo.registry] registry unavailable during import"
    )