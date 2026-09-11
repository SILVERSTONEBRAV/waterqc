# ==========================================================
# kstw/registry.py
# ==========================================================

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

APP_LABEL = "kstw"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================

def get_model(name: str):
    """
    Lazily resolve models.

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
            "[kstw.registry] Unable to resolve %s.%s",
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

IndustrialSample = get_model(
    "IndustrialSample"
)

IndustrialSampleAnalysis = get_model(
    "IndustrialSampleAnalysis"
)

IndustrialSampleParameterResult = get_model(
    "IndustrialSampleParameterResult"
)

TreatmentPlantSample = get_model(
    "TreatmentPlantSample"
)

TreatmentPlantSampleAnalysis = get_model(
    "TreatmentPlantSampleAnalysis"
)

TreatmentPlantSampleParameterResult = get_model(
    "TreatmentPlantSampleParameterResult"
)

ExhausterSample = get_model(
    "ExhausterSample"
)

ExhausterSampleAnalysis = get_model(
    "ExhausterSampleAnalysis"
)

ExhausterSampleParameterResult = get_model(
    "ExhausterSampleParameterResult"
)


# ==========================================================
# ICON MAP
# ==========================================================

ICONS = {

    "WasteWaterSamplingSite": "location-dot",

    "WasteWaterSample": "vial",
    "WasteWaterAnalysis": "flask",
    "WasteWaterParameterResult": "microscope",

    "IndustrialSample": "industry",
    "IndustrialSampleAnalysis": "flask-vial",
    "IndustrialSampleParameterResult": "chart-column",

    "TreatmentPlantSample": "water",
    "TreatmentPlantSampleAnalysis": "flask-vial",
    "TreatmentPlantSampleParameterResult": "chart-column",

    "ExhausterSample": "truck",
    "ExhausterSampleAnalysis": "flask-vial",
    "ExhausterSampleParameterResult": "chart-column",

}


# ==========================================================
# GROUP MAP
# ==========================================================

GROUPS = {

    "WasteWaterSamplingSite": "sampling",

    "WasteWaterSample": "wastewater",
    "WasteWaterAnalysis": "wastewater",
    "WasteWaterParameterResult": "wastewater",

    "IndustrialSample": "industrial",
    "IndustrialSampleAnalysis": "industrial",
    "IndustrialSampleParameterResult": "industrial",

    "TreatmentPlantSample": "treatment",
    "TreatmentPlantSampleAnalysis": "treatment",
    "TreatmentPlantSampleParameterResult": "treatment",

    "ExhausterSample": "exhauster",
    "ExhausterSampleAnalysis": "exhauster",
    "ExhausterSampleParameterResult": "exhauster",

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
# INTERNAL HELPERS
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


def sample_qs(model) -> QuerySet:
    """
    Generic sample queryset.

    Automatically adapts to
    every sample model.
    """

    return model.objects.select_related(

        *existing(

            model,

            "treatment_plant",

            "sampling_site",

            "shift",

            "assignment",

            "analysis",

        )

    )


def analysis_qs(model) -> QuerySet:
    """
    Generic analysis queryset.
    """

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

    if hasattr(
        model,
        "parameter_results",
    ):

        qs = qs.prefetch_related(
            "parameter_results"
        )

    return qs


def parameter_result_qs(model) -> QuerySet:
    """
    Generic parameter-result queryset.
    """

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

SAMPLE_BASE_CONFIG = {

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


ANALYSIS_BASE_CONFIG = {

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


PARAMETER_RESULT_BASE_CONFIG = {

    "search_fields": [

        "parameter__name",

        "analysis__sample__reference_id",

    ],

    "filter_fields": [

        "parameter",

        "analysis",

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


SAMPLING_SITE_BASE_CONFIG = {

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

}


# ==========================================================
# SAFE REGISTRATION WRAPPER
# ==========================================================

def safe_register(
    model,
    **kwargs,
):
    """
    Normalizes every registration.

    Automatically injects

        • metadata
        • UI
        • safety defaults

    keeping every registry consistent.
    """

    if model is None:

        raise RuntimeError(
            "Model resolution failed."
        )

    # ------------------------------------------------------
    # META
    # ------------------------------------------------------

    meta = kwargs.get(
        "meta",
        {},
    )

    meta.update(
        build_meta(model)
    )

    kwargs["meta"] = meta

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # REMOVE UNUSED KEYS
    # ------------------------------------------------------

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

            "[kstw.registry] Failed registering %s",

            model.__name__,

        )

        raise


# ==========================================================
# REGISTRATION HELPERS
# ==========================================================

def register_sample(
    model,
    **extra,
):
    """
    Register any sample model.
    """

    config = SAMPLE_BASE_CONFIG.copy()

    config.update(extra)

    safe_register(
        model,
        **config,
    )


def register_analysis(
    model,
    **extra,
):
    """
    Register any analysis model.
    """

    config = ANALYSIS_BASE_CONFIG.copy()

    config.update(extra)

    safe_register(
        model,
        **config,
    )


def register_parameter_result(
    model,
    **extra,
):
    """
    Register any parameter result model.
    """

    config = PARAMETER_RESULT_BASE_CONFIG.copy()

    config.update(extra)

    safe_register(
        model,
        **config,
    )


def register_sampling_site(
    model,
    **extra,
):
    """
    Register sampling site model.
    """

    config = SAMPLING_SITE_BASE_CONFIG.copy()

    config.update(extra)

    safe_register(
        model,
        **config,
    )


# ==========================================================
# MODEL SPECIFIC CONFIGURATION
# ==========================================================

WW_SAMPLE_FIELDS = [

    "reference_id",

    "treatment_plant",

    "sampling_site",

    "sampling_date",

    "sampling_time",

    "shift",

]

INDUSTRIAL_SAMPLE_FIELDS = [

    "reference_id",

    "client_name",

    "location",

    "sampling_date",

    "sampling_time",

    "shift",

]

PLANT_SAMPLE_FIELDS = [

    "reference_id",

    "treatment_plant",

    "sampling_point_description",

    "sampling_date",

    "sampling_time",

    "shift",

]

EXHAUSTER_SAMPLE_FIELDS = [

    "reference_id",

    "exhauster_reg_number",

    "driver_name",

    "sampling_date",

    "sampling_time",

    "shift",

]


ANALYSIS_FIELDS = [

    "sample",

    "status",

    "analysis_datetime",

    "analysed_by",

    "verified_by",

    "confirmed_by",

    "approved_by",

]


PARAMETER_FIELDS = [

    "analysis",

    "parameter",

    "result",

    "quality_compliance",

    "analysis_method",

]
# ==========================================================
# WASTE WATER SAMPLING SITE
# ==========================================================

register_sampling_site(

    WasteWaterSamplingSite,

    list_display=[

        "name",

        "treatment_plant",

        "location_description",

        "created_at",

    ],

    list_select_related=[

        "treatment_plant",

    ],

    inline_edit_fields=[

        "name",

        "location_description",

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
# INDUSTRIAL SAMPLE
# ==========================================================

register_sample(

    IndustrialSample,

    search_fields=[

        "reference_id",

        "client_name",

        "location",

    ],

    filter_fields=[

        "sampling_date",

        "shift",

        "assignment",

    ],

    list_display=INDUSTRIAL_SAMPLE_FIELDS,

    list_select_related=[

        "shift",

        "assignment",

        "analysis",

    ],

    export_fields=[

        "reference_id",

        "client_name",

        "location",

        "sampling_date",

        "sampling_time",

        "shift",

        "assignment",

    ],

)


# ==========================================================
# TREATMENT PLANT SAMPLE
# ==========================================================

register_sample(

    TreatmentPlantSample,

    search_fields=[

        "reference_id",

        "treatment_plant__name",

        "sampling_point_description",

    ],

    filter_fields=[

        "treatment_plant",

        "sampling_date",

        "shift",

        "assignment",

    ],

    list_display=PLANT_SAMPLE_FIELDS,

    list_select_related=[

        "treatment_plant",

        "shift",

        "assignment",

        "analysis",

    ],

    export_fields=[

        "reference_id",

        "treatment_plant",

        "sampling_point_description",

        "sampling_date",

        "sampling_time",

        "shift",

        "assignment",

    ],

)


# ==========================================================
# EXHAUSTER SAMPLE
# ==========================================================

register_sample(

    ExhausterSample,

    search_fields=[

        "reference_id",

        "exhauster_reg_number",

        "driver_name",

    ],

    filter_fields=[

        "sampling_date",

        "shift",

        "assignment",

    ],

    list_display=EXHAUSTER_SAMPLE_FIELDS,

    list_select_related=[

        "shift",

        "assignment",

        "analysis",

    ],

    export_fields=[

        "reference_id",

        "exhauster_reg_number",

        "driver_name",

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

    list_display=ANALYSIS_FIELDS,

    list_select_related=[

        "sample",

        "analysed_by",

        "verified_by",

        "confirmed_by",

        "approved_by",

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
# INDUSTRIAL ANALYSIS
# ==========================================================

register_analysis(

    IndustrialSampleAnalysis,

    list_display=ANALYSIS_FIELDS,

    list_select_related=[

        "sample",

        "analysed_by",

        "verified_by",

        "confirmed_by",

        "approved_by",

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
# TREATMENT PLANT ANALYSIS
# ==========================================================

register_analysis(

    TreatmentPlantSampleAnalysis,

    list_display=ANALYSIS_FIELDS,

    list_select_related=[

        "sample",

        "analysed_by",

        "verified_by",

        "confirmed_by",

        "approved_by",

    ],

)


# ==========================================================
# EXHAUSTER ANALYSIS
# ==========================================================

register_analysis(

    ExhausterSampleAnalysis,

    list_display=ANALYSIS_FIELDS,

    list_select_related=[

        "sample",

        "analysed_by",

        "verified_by",

        "confirmed_by",

        "approved_by",

    ],

)


# ==========================================================
# PARAMETER RESULTS
# ==========================================================

register_parameter_result(

    WasteWaterParameterResult,

    list_display=PARAMETER_FIELDS,

    list_select_related=[

        "analysis",

        "parameter",

        "analysis_method",

    ],

)

register_parameter_result(

    IndustrialSampleParameterResult,

    list_display=PARAMETER_FIELDS,

    list_select_related=[

        "analysis",

        "parameter",

        "analysis_method",

    ],

)

register_parameter_result(

    TreatmentPlantSampleParameterResult,

    list_display=PARAMETER_FIELDS,

    list_select_related=[

        "analysis",

        "parameter",

        "analysis_method",

    ],

)

register_parameter_result(

    ExhausterSampleParameterResult,

    list_display=PARAMETER_FIELDS,

    list_select_related=[

        "analysis",

        "parameter",

        "analysis_method",

    ],

)


# ==========================================================
# REGISTRY VERIFICATION
# ==========================================================

try:

    from core.registry import registry

    logger.info(

        "[kstw.registry] Loaded %s (%d models)",

        APP_LABEL,

        len(
            getattr(
                registry,
                "_registry",
                {},
            )
        ),

    )

except Exception:

    logger.exception(

        "[kstw.registry] Registry verification failed."

    )