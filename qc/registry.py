from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from django.apps import apps
from django.db.models import Prefetch, QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "qc"


@lru_cache(maxsize=None)
def get_model(name: str):
    return apps.get_model(APP_LABEL, name)


SamplingSchedule = get_model("SamplingSchedule")
SamplingTime = get_model("SamplingTime")

WaterAnalysis = get_model("WaterAnalysis")
WaterAnalysisLog = get_model("WaterAnalysisLog")

RawWaterResult = get_model("RawWaterResult")
TreatedWaterResult = get_model("TreatedWaterResult")
CoagulatedWaterResult = get_model("CoagulatedWaterResult")
ClarifiedWaterResult = get_model("ClarifiedWaterResult")

NonConformity = get_model("NonConformity")
NonConformityLog = get_model("NonConformityLog")
Cause = get_model("Cause")


WATER_RESULT_MODELS = {
    SamplingSchedule.RAW: RawWaterResult,
    SamplingSchedule.TREATED: TreatedWaterResult,
    SamplingSchedule.COAGULATED: CoagulatedWaterResult,
    SamplingSchedule.CLARIFIED: ClarifiedWaterResult,
}


ICONS = {
    "SamplingSchedule": "calendar-days",
    "SamplingTime": "clock",
    "WaterAnalysis": "flask-vial",
    "WaterAnalysisLog": "clipboard-list",
    "RawWaterResult": "water",
    "TreatedWaterResult": "glass-water",
    "CoagulatedWaterResult": "vial",
    "ClarifiedWaterResult": "droplet",
    "NonConformity": "triangle-exclamation",
    "NonConformityLog": "list-check",
    "Cause": "circle-exclamation",
}


GROUPS = {
    "SamplingSchedule": "sampling",
    "SamplingTime": "sampling",
    "WaterAnalysis": "analysis",
    "WaterAnalysisLog": "analysis",
    "RawWaterResult": "results",
    "TreatedWaterResult": "results",
    "CoagulatedWaterResult": "results",
    "ClarifiedWaterResult": "results",
    "NonConformity": "compliance",
    "NonConformityLog": "compliance",
    "Cause": "compliance",
}


_REGISTERED: set[str] = set()


def build_meta(model) -> dict[str, Any]:
    opts = model._meta

    return {
        "key": f"{opts.app_label}.{opts.model_name}",
        "app_label": opts.app_label,
        "model_name": opts.model_name,
        "verbose_name": str(opts.verbose_name),
        "verbose_name_plural": str(opts.verbose_name_plural),
    }


def build_ui(model) -> dict[str, Any]:
    return {
        "icon": ICONS.get(model.__name__, "cube"),
        "group": GROUPS.get(model.__name__, "general"),
    }


def safe_register(model, **kwargs):
    key = f"{model._meta.app_label}.{model._meta.model_name}"

    if key in _REGISTERED:
        return model

    kwargs["meta"] = {
        **build_meta(model),
        **kwargs.get("meta", {}),
    }

    kwargs["ui"] = {
        **build_ui(model),
        **kwargs.get("ui", {}),
    }

    kwargs.pop("templates", None)

    register_model(**kwargs)(model)

    _REGISTERED.add(key)

    return model
def schedule_queryset(model) -> QuerySet:
    return (
        model.objects
        .select_related("treatment_plant")
        .prefetch_related(
            Prefetch(
                "sampling_times",
                queryset=SamplingTime.objects.order_by("time"),
            ),
        )
    )


def sampling_time_queryset(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "schedule",
            "schedule__treatment_plant",
        )
    )


def analysis_queryset(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "treatment_plant",
            "analysis_time",
            "analysis_time__schedule",
            "shift",
        )
        .prefetch_related(
            "logs",
            "nonconformities",
            "rawwaterresults",
            "treatedwaterresults",
            "coagulatedwaterresults",
            "clarifiedwaterresults",
        )
    )


def analysis_log_queryset(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "analysis",
            "analysis__treatment_plant",
            "actor",
        )
    )


def result_queryset(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "analysis",
            "analysis__treatment_plant",
            "analysis__analysis_time",
            "analysis__shift",
            "phase",
            "parameter",
            "parameter__parameter",
        )
    )


def nonconformity_queryset(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "analysis",
            "analysis__treatment_plant",
            "analysis__analysis_time",
            "triggered_by",
            "reviewed_by",
        )
        .prefetch_related(
            "causes",
            "logs",
        )
    )


def nonconformity_log_queryset(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "nonconformity",
            "nonconformity__analysis",
            "actor",
        )
    )


def cause_queryset(model) -> QuerySet:
    return (
        model.objects
        .select_related(
            "created_by",
        )
        .prefetch_related(
            "nonconformities",
        )
    )
safe_register(
    SamplingSchedule,
    search_fields=[
        "treatment_plant__name",
        "water_type",
    ],
    filter_fields=[
        "treatment_plant",
        "water_type",
        "enabled",
    ],
    ordering=[
        "treatment_plant__name",
        "water_type",
    ],
    queryset_factory=schedule_queryset,
)


safe_register(
    SamplingTime,
    search_fields=[
        "schedule__treatment_plant__name",
        "schedule__water_type",
    ],
    filter_fields=[
        "schedule",
        "schedule__water_type",
    ],
    ordering=[
        "schedule__water_type",
        "time",
    ],
    queryset_factory=sampling_time_queryset,
)


safe_register(
    WaterAnalysis,
    search_fields=[
        "reference_id",
        "treatment_plant__name",
        "remarks",
    ],
    filter_fields=[
        "treatment_plant",
        "analysis_date",
        "shift",
        "analysis_time__schedule__water_type",
    ],
    ordering=[
        "-analysis_date",
        "-analysis_time__time",
    ],
    queryset_factory=analysis_queryset,
)


safe_register(
    WaterAnalysisLog,
    search_fields=[
        "analysis__reference_id",
        "action",
        "remarks",
    ],
    filter_fields=[
        "analysis",
        "actor",
        "auto_generated",
    ],
    ordering=[
        "-created_at",
    ],
    queryset_factory=analysis_log_queryset,
)
for model in WATER_RESULT_MODELS.values():
    safe_register(
        model,
        search_fields=[
            "analysis__reference_id",
            "parameter__parameter__name",
            "analysis__treatment_plant__name",
        ],
        filter_fields=[
            "analysis",
            "analysis__treatment_plant",
            "analysis__analysis_date",
            "analysis__shift",
            "phase",
        ],
        ordering=[
            "-analysis__analysis_date",
            "analysis__analysis_time__time",
            "phase__name",
            "parameter__parameter__name",
        ],
        queryset_factory=result_queryset,
        inline_edit_fields=[
            "value",
        ],
    )
    safe_register(
        NonConformity,
        search_fields=[
            "parameter_name",
            "analysis__reference_id",
            "analysis__treatment_plant__name",
            "corrective_action",
            "preventive_action",
            "root_cause",
        ],
        filter_fields=[
            "status",
            "analysis",
            "analysis__treatment_plant",
            "auto_detected",
            "triggered_by",
            "reviewed_by",
            "escalation_level",
        ],
        ordering=[
            "-created_at",
        ],
        queryset_factory=nonconformity_queryset,
    )

    safe_register(
        NonConformityLog,
        search_fields=[
            "action",
            "remarks",
            "nonconformity__parameter_name",
            "nonconformity__analysis__reference_id",
        ],
        filter_fields=[
            "nonconformity",
            "actor",
            "auto_generated",
        ],
        ordering=[
            "-created_at",
        ],
        queryset_factory=nonconformity_log_queryset,
    )

    safe_register(
        Cause,
        search_fields=[
            "name",
            "description",
        ],
        filter_fields=[
            "created_by",
        ],
        ordering=[
            "name",
        ],
        queryset_factory=cause_queryset,
    )


    def get_result_model(water_type: str):
        try:
            return WATER_RESULT_MODELS[water_type]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported water type: {water_type}"
            ) from exc


    def get_result_queryset_for_analysis(analysis) -> QuerySet:
        model = get_result_model(analysis.water_type)

        return (
            model.objects
            .filter(
                analysis=analysis,
            )
            .select_related(
                "analysis",
                "analysis__treatment_plant",
                "analysis__analysis_time",
                "analysis__shift",
                "phase",
                "parameter",
                "parameter__parameter",
            )
        )


    def get_registry_models() -> tuple[type, ...]:
        return (
            SamplingSchedule,
            SamplingTime,
            WaterAnalysis,
            WaterAnalysisLog,
            RawWaterResult,
            TreatedWaterResult,
            CoagulatedWaterResult,
            ClarifiedWaterResult,
            NonConformity,
            NonConformityLog,
            Cause,
        )


    try:
        from core.registry import registry

        logger.info(
            "QC registry loaded (%d models)",
            len(getattr(registry, "_registry", {})),
        )

    except Exception:
        logger.exception(
            "Failed to initialize QC registry."
        )