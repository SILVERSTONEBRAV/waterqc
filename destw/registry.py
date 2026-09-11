from __future__ import annotations

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import (
    ForeignKey,
    OneToOneField,
    QuerySet,
)

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "destw"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================

def get_model(name: str):
    """
    Lazy model resolver.

    Prevents circular imports and
    AppRegistryNotReady errors.
    """

    try:
        return apps.get_model(
            APP_LABEL,
            name,
        )

    except LookupError:

        logger.exception(
            "[destw.registry] Unable to resolve %s.%s",
            APP_LABEL,
            name,
        )

        return None


# ==========================================================
# MODEL REFERENCES
# ==========================================================

WasteWaterSamplingSite = get_model(
    "WasteWaterSamplingSite"
)

WasteWaterSample = get_model(
    "WasteWaterSample"
)

WasteWaterAnalysis = get_model(
    "WasteWaterAnalysis"
)

WasteWaterParameterResult = get_model(
    "WasteWaterParameterResult"
)

WasteWaterStabilizationPond = get_model(
    "WasteWaterStabilizationPond"
)

WasteWaterPondSamplingSite = get_model(
    "WasteWaterPondSamplingSite"
)

WasteWaterPondSample = get_model(
    "WasteWaterPondSample"
)

WasteWaterPondAnalysis = get_model(
    "WasteWaterPondAnalysis"
)

WasteWaterPondParameterResult = get_model(
    "WasteWaterPondParameterResult")


# ==========================================================
# ICON MAP
# ==========================================================

ICONS = {

    "WasteWaterSamplingSite":
        "location-dot",

    "WasteWaterSample":
        "vial",

    "WasteWaterAnalysis":
        "flask",

    "WasteWaterParameterResult":
        "chart-line",

    "WasteWaterStabilizationPond":
        "water",

    "WasteWaterPondSamplingSite":
        "location-dot",

    "WasteWaterPondSample":
        "vial-circle-check",

    "WasteWaterPondAnalysis":
        "microscope",

    "WasteWaterPondParameterResult":
        "chart-column",

}


# ==========================================================
# GROUP MAP
# ==========================================================

GROUPS = {

    "WasteWaterSamplingSite":
        "sampling",

    "WasteWaterSample":
        "sampling",

    "WasteWaterAnalysis":
        "analysis",

    "WasteWaterParameterResult":
        "analysis",

    "WasteWaterStabilizationPond":
        "ponds",

    "WasteWaterPondSamplingSite":
        "ponds",

    "WasteWaterPondSample":
        "ponds",

    "WasteWaterPondAnalysis":
        "ponds",

    "WasteWaterPondParameterResult":
        "ponds",

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

    verbose = humanize_model_name(
        model
    )

    return {

        "key":
            f"{model._meta.app_label}."
            f"{model._meta.model_name}",

        "app_label":
            model._meta.app_label,

        "model_name":
            model._meta.model_name,

        "verbose_name":
            verbose,

        "verbose_name_plural":
            f"{verbose}s",

    }


# ==========================================================
# INTERNAL RELATION HELPERS
# ==========================================================

def relation_fields(model):

    return {

        field.name

        for field in model._meta.get_fields()

        if isinstance(

            field,

            (
                ForeignKey,
                OneToOneField,
            ),

        )

    }


def existing(model, *fields):

    available = relation_fields(model)

    return [

        field

        for field in fields

        if field in available

    ]


# ==========================================================
# QUERYSET FACTORIES
# ==========================================================

def sampling_site_qs(model) -> QuerySet:
    """
    WasteWaterSamplingSite
    """

    return model.objects.select_related(

        *existing(

            model,

            "treatment_plant",

        )

    )


def stabilization_pond_qs(model):

    return model.objects.select_related(

        *existing(

            model,

            "treatment_plant",

        )

    )


def pond_sampling_site_qs(model):

    return model.objects.select_related(

        *existing(

            model,

            "pond",

        )

    )


def sample_qs(model):
    """
    Automatically adapts to every sample model.
    """

    return model.objects.select_related(

        *existing(

            model,

            "treatment_plant",

            "sampling_site",

            "site",

            "pond",

            "shift",

            "assignment",

            "analysis",

        )

    )


def analysis_qs(model):

    qs = model.objects.select_related(

        *existing(

            model,

            "sample",

            "analysed_by",

            "verified_by",

            "confirmed_by",

            "approved_by",

        )

    )

    reverse = [

        r.get_accessor_name()

        for r in model._meta.related_objects

    ]

    if "destw_parameter_results" in reverse:

        qs = qs.prefetch_related(
            "destw_parameter_results"
        )

    if "destw_pond_parameter_results" in reverse:

        qs = qs.prefetch_related(
            "destw_pond_parameter_results"
        )

    return qs


def parameter_result_qs(model):

    return model.objects.select_related(

        *existing(

            model,

            "analysis",

            "parameter",

            "analysis_method",

        )

    )
# ==========================================================
# SHARED CONFIGURATION
# ==========================================================

SAMPLING_SITE_CONFIG = {

    "search_fields": [
        "name",
        "location_description",
        "treatment_plant__name",
    ],

    "filter_fields": [
        "treatment_plant",
    ],

    "ordering": [
        "name",
    ],

    "queryset_factory": sampling_site_qs,

    "inline_edit_fields": [
        "name",
        "location_description",
    ],

}


STABILIZATION_POND_CONFIG = {

    "search_fields": [

        "name",

        "treatment_plant__name",

    ],

    "filter_fields": [

        "treatment_plant",

    ],

    "ordering": [

        "name",

    ],

    "queryset_factory": stabilization_pond_qs,

    "inline_edit_fields": [

        "name",

        "description",

    ],

}


POND_SAMPLING_SITE_CONFIG = {

    "search_fields": [

        "site_name",

        "pond__name",

    ],

    "filter_fields": [

        "pond",

    ],

    "ordering": [

        "site_name",

    ],

    "queryset_factory": pond_sampling_site_qs,

    "inline_edit_fields": [

        "site_name",

        "description",

    ],

}


SAMPLE_CONFIG = {

    "search_fields": [

        "reference_id",

    ],

    "filter_fields": [

        "sampling_date",

        "shift",

    ],

    "ordering": [

        "-sampling_date",

        "-sampling_time",

    ],

    "queryset_factory": sample_qs,

    "bulk_actions": {

        "delete_selected": True,

        "export": True,

    },

}


ANALYSIS_CONFIG = {

    "search_fields": [

        "sample__reference_id",

        "remarks",

    ],

    "filter_fields": [

        "status",

        "analysis_datetime",

    ],

    "ordering": [

        "-analysis_datetime",

    ],

    "queryset_factory": analysis_qs,

    "inline_edit_fields": [

        "remarks",

    ],

    "bulk_actions": {

        "analyse": True,

        "verify": True,

        "confirm": True,

        "approve": True,

        "export": True,

    },

}


PARAMETER_RESULT_CONFIG = {

    "search_fields": [

        "parameter__name",

        "analysis__sample__reference_id",

    ],

    "filter_fields": [

        "analysis",

        "parameter",

        "analysis_method",

    ],

    "ordering": [

        "parameter",

    ],

    "queryset_factory": parameter_result_qs,

    "inline_edit_fields": [

        "result",

    ],

}


# ==========================================================
# REGISTRATION WRAPPER
# ==========================================================

def safe_register(
    model,
    **kwargs,
):
    """
    Production-safe registry wrapper.

    Adds metadata.

    Adds UI defaults.

    Removes unsupported kwargs.

    Prevents duplicated configuration.
    """

    if model is None:

        raise RuntimeError(
            "Model resolution failed."
        )

    # --------------------------------------------------
    # metadata
    # --------------------------------------------------

    meta = kwargs.get(
        "meta",
        {},
    )

    meta.update(
        build_meta(model)
    )

    kwargs["meta"] = meta

    # --------------------------------------------------
    # ui
    # --------------------------------------------------

    ui = kwargs.get(
        "ui",
        {},
    )

    ui.setdefault(

        "icon",

        ICONS.get(
            model.__name__,
            "cube",
        ),

    )

    ui.setdefault(

        "group",

        GROUPS.get(
            model.__name__,
            "general",
        ),

    )

    kwargs["ui"] = ui

    # --------------------------------------------------
    # cleanup
    # --------------------------------------------------

    kwargs.pop(
        "templates",
        None,
    )

    try:

        return register_model(
            **kwargs
        )(model)

    except Exception:

        logger.exception(

            "[destw.registry] Failed registering %s",

            model.__name__,

        )

        raise


# ==========================================================
# REGISTRATION HELPERS
# ==========================================================

def register_sampling_site(
    model,
    **extra,
):

    config = SAMPLING_SITE_CONFIG.copy()

    config.update(extra)

    safe_register(
        model,
        **config,
    )


def register_stabilization_pond(
    model,
    **extra,
):

    config = STABILIZATION_POND_CONFIG.copy()

    config.update(extra)

    safe_register(
        model,
        **config,
    )


def register_pond_sampling_site(
    model,
    **extra,
):

    config = POND_SAMPLING_SITE_CONFIG.copy()

    config.update(extra)

    safe_register(
        model,
        **config,
    )


def register_sample(
    model,
    **extra,
):

    config = SAMPLE_CONFIG.copy()

    config.update(extra)

    safe_register(
        model,
        **config,
    )


def register_analysis(
    model,
    **extra,
):

    config = ANALYSIS_CONFIG.copy()

    config.update(extra)

    safe_register(
        model,
        **config,
    )


def register_parameter_result(
    model,
    **extra,
):

    config = PARAMETER_RESULT_CONFIG.copy()

    config.update(extra)

    safe_register(
        model,
        **config,
    )


# ==========================================================
# COMMON DISPLAY DEFINITIONS
# ==========================================================

SAMPLING_SITE_FIELDS = [

    "name",

    "treatment_plant",

    "location_description",

]


STABILIZATION_POND_FIELDS = [

    "name",

    "treatment_plant",

    "description",

]


POND_SAMPLING_SITE_FIELDS = [

    "site_name",

    "pond",

    "description",

]


SAMPLE_FIELDS = [

    "reference_id",

    "sampling_date",

    "sampling_time",

    "shift",

]


WW_SAMPLE_FIELDS = [

    "reference_id",

    "treatment_plant",

    "sampling_site",

    "sampling_date",

    "sampling_time",

    "shift",

]


POND_SAMPLE_FIELDS = [

    "reference_id",

    "site",

    "sampling_date",

    "sampling_time",

    "shift",

]


ANALYSIS_FIELDS = [

    "sample",

    "status",

    "analysis_datetime",

]


PARAMETER_FIELDS = [

    "analysis",

    "parameter",

    "result",

    "quality_compliance",

]
# ==========================================================
# WASTE WATER SAMPLING SITE
# ==========================================================

register_sampling_site(

    WasteWaterSamplingSite,

    list_display=SAMPLING_SITE_FIELDS,

    list_select_related=[
        "treatment_plant",
    ],

    export_fields=[
        "name",
        "treatment_plant",
        "location_description",
        "created_at",
    ],

)


# ==========================================================
# WASTE WATER SAMPLE
# ==========================================================

register_sample(

    WasteWaterSample,

    search_fields=[
        "reference_id",
        "sampling_site__name",
        "treatment_plant__name",
    ],

    filter_fields=[
        "treatment_plant",
        "sampling_site",
        "sampling_date",
        "shift",
        "assignment",
    ],

    list_display=WW_SAMPLE_FIELDS,

    list_select_related=[
        "treatment_plant",
        "sampling_site",
        "shift",
        "assignment",
        "destw_analysis",
    ],

    inline_edit_fields=[
        "sampling_date",
        "sampling_time",
    ],

    export_fields=[
        "reference_id",
        "treatment_plant",
        "sampling_site",
        "sampling_date",
        "sampling_time",
        "shift",
        "assignment",
    ],

)


# ==========================================================
# WASTE WATER ANALYSIS
# ==========================================================

register_analysis(

    WasteWaterAnalysis,

    list_display=[

        "sample",

        "status",

        "analysis_datetime",

        "analysed_by",

        "verified_by",

        "confirmed_by",

        "approved_by",

    ],

    list_select_related=[

        "sample",

        "analysed_by",

        "verified_by",

        "confirmed_by",

        "approved_by",

    ],

    inline_edit_fields=[

        "remarks",

    ],

    export_fields=[

        "sample",

        "status",

        "analysis_datetime",

        "remarks",

        "analysed_by",

        "verified_by",

        "confirmed_by",

        "approved_by",

    ],

)


# ==========================================================
# WASTE WATER PARAMETER RESULTS
# ==========================================================

register_parameter_result(

    WasteWaterParameterResult,

    list_display=[

        "analysis",

        "parameter",

        "result",

        "quality_compliance",

        "analysis_method",

    ],

    list_select_related=[

        "analysis",

        "parameter",

        "analysis_method",

    ],

    inline_edit_fields=[

        "result",

    ],

    export_fields=[

        "analysis",

        "parameter",

        "analysis_method",

        "result",

        "quality_compliance",

        "effluent_standard",

        "kebs_reference",

    ],

)
# ==========================================================
# STABILIZATION PONDS
# ==========================================================

register_stabilization_pond(

    WasteWaterStabilizationPond,

    list_display=[

        "name",

        "treatment_plant",

        "description",

    ],

    list_select_related=[

        "treatment_plant",

    ],

    export_fields=[

        "name",

        "treatment_plant",

        "description",

        "created_at",

    ],

)


# ==========================================================
# POND SAMPLING SITES
# ==========================================================

register_pond_sampling_site(

    WasteWaterPondSamplingSite,

    search_fields=[

        "site_name",

        "pond__name",

        "pond__treatment_plant__name",

    ],

    filter_fields=[

        "pond",

    ],

    list_display=[

        "site_name",

        "pond",

        "description",

    ],

    list_select_related=[

        "pond",

    ],

    inline_edit_fields=[

        "site_name",

        "description",

    ],

    export_fields=[

        "site_name",

        "pond",

        "description",

        "created_at",

    ],

)


# ==========================================================
# POND SAMPLES
# ==========================================================

register_sample(

    WasteWaterPondSample,

    search_fields=[

        "reference_id",

        "site__site_name",

        "site__pond__name",

    ],

    filter_fields=[

        "site",

        "sampling_date",

        "shift",

        "assignment",

    ],

    list_display=POND_SAMPLE_FIELDS,

    list_select_related=[

        "site",

        "shift",

        "assignment",

        "destw_pond_analysis",

    ],

    inline_edit_fields=[

        "sampling_date",

        "sampling_time",

    ],

    export_fields=[

        "reference_id",

        "site",

        "sampling_date",

        "sampling_time",

        "shift",

        "assignment",

    ],

)


# ==========================================================
# POND ANALYSIS
# ==========================================================

register_analysis(

    WasteWaterPondAnalysis,

    list_display=[

        "sample",

        "status",

        "analysis_datetime",

        "analysed_by",

        "verified_by",

        "confirmed_by",

        "approved_by",

    ],

    list_select_related=[

        "sample",

        "analysed_by",

        "verified_by",

        "confirmed_by",

        "approved_by",

    ],

    inline_edit_fields=[

        "remarks",

    ],

    export_fields=[

        "sample",

        "status",

        "analysis_datetime",

        "remarks",

        "analysed_by",

        "verified_by",

        "confirmed_by",

        "approved_by",

    ],

)


# ==========================================================
# POND PARAMETER RESULTS
# ==========================================================

register_parameter_result(

    WasteWaterPondParameterResult,

    list_display=[

        "analysis",

        "parameter",

        "result",

        "quality_compliance",

        "analysis_method",

    ],

    list_select_related=[

        "analysis",

        "parameter",

        "analysis_method",

    ],

    inline_edit_fields=[

        "result",

    ],

    export_fields=[

        "analysis",

        "parameter",

        "analysis_method",

        "result",

        "quality_compliance",

        "effluent_standard",

        "kebs_reference",

    ],

)


# ==========================================================
# REGISTRY VALIDATION
# ==========================================================

try:

    from core.registry import registry

    total = len(
        getattr(
            registry,
            "_registry",
            {},
        )
    )

    logger.info(

        "[destw.registry] Loaded app=%s (%d registered models)",

        APP_LABEL,

        total,

    )

except Exception:

    logger.exception(

        "[destw.registry] Registry unavailable during startup."

    )