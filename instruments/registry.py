# instruments/registry.py

import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "instruments"


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
Instrument = get_model("Instrument")
Sensor = get_model("Sensor")
OnlineMeasurement = get_model("OnlineMeasurement")
DerivedMetric = get_model("DerivedMetric")
InstrumentCalibration = get_model("InstrumentCalibration")
SensorHealthSnapshot = get_model("SensorHealthSnapshot")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "Instrument": "microchip",
    "Sensor": "gauge-high",
    "OnlineMeasurement": "wave-square",
    "DerivedMetric": "chart-line",
    "InstrumentCalibration": "screwdriver-wrench",
    "SensorHealthSnapshot": "heart-pulse",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "Instrument": "devices",
    "Sensor": "devices",
    "OnlineMeasurement": "telemetry",
    "DerivedMetric": "analytics",
    "InstrumentCalibration": "maintenance",
    "SensorHealthSnapshot": "health",
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
def instrument_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "phase",
    ).prefetch_related(
        "sensors",
        "calibrations",
    )


def sensor_qs(model) -> QuerySet:
    return model.objects.select_related(
        "instrument",
        "parameter",
        "treatment_plant",
        "phase",
    )


def measurement_qs(model) -> QuerySet:
    return model.objects.select_related(
        "sensor",
        "sensor__instrument",
        "treatment_plant",
        "phase",
    )


def metric_qs(model) -> QuerySet:
    return model.objects.select_related(
        "sensor",
        "sensor__instrument",
        "treatment_plant",
        "phase",
    )


def calibration_qs(model) -> QuerySet:
    return model.objects.select_related(
        "instrument",
        "instrument__treatment_plant",
    )


def health_qs(model) -> QuerySet:
    return model.objects.select_related(
        "sensor",
        "sensor__instrument",
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
        ICONS.get(model.__name__, "cube")
    )
    ui.setdefault(
        "group",
        GROUPS.get(model.__name__, "general")
    )

    kwargs["ui"] = ui
    kwargs.pop("templates", None)

    try:
        return register_model(**kwargs)(model)

    except Exception:
        logger.exception(
            "[instruments.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# INSTRUMENT
# ==========================================================
safe_register(
    Instrument,
    search_fields=[
        "name",
        "manufacturer",
        "model",
        "serial_number",
        "ip_address",
    ],
    filter_fields=[
        "status",
        "protocol",
        "treatment_plant",
        "phase",
        "is_active",
    ],
    ordering=[
        "name",
    ],
    select_related=[
        "treatment_plant",
        "phase",
    ],
    prefetch_related=[
        "sensors",
        "calibrations",
    ],
    queryset_factory=instrument_qs,
    inline_edit_fields=[
        "name",
        "status",
        "protocol",
        "ip_address",
        "is_active",
    ],
    bulk_actions={
        "mark_online": True,
        "mark_offline": True,
        "refresh_health": True,
    },
)


# ==========================================================
# SENSOR
# ==========================================================
safe_register(
    Sensor,
    search_fields=[
        "name",
        "parameter__name",
        "instrument__name",
    ],
    filter_fields=[
        "stage",
        "parameter",
        "instrument",
        "treatment_plant",
        "phase",
        "is_primary",
        "is_active",
    ],
    ordering=[
        "parameter__name",
        "name",
    ],
    select_related=[
        "instrument",
        "parameter",
        "treatment_plant",
        "phase",
    ],
    queryset_factory=sensor_qs,
    inline_edit_fields=[
        "name",
        "stage",
        "is_primary",
        "is_active",
        "drift_threshold",
    ],
)


# ==========================================================
# ONLINE MEASUREMENTS
# ==========================================================
safe_register(
    OnlineMeasurement,
    search_fields=[
        "sensor__name",
        "sensor__parameter__name",
        "source",
    ],
    filter_fields=[
        "quality_flag",
        "sensor",
        "treatment_plant",
        "phase",
        "source",
    ],
    ordering=[
        "-measured_at",
    ],
    select_related=[
        "sensor",
        "treatment_plant",
        "phase",
    ],
    queryset_factory=measurement_qs,
    inline_edit_fields=[
        "quality_flag",
        "anomaly_score",
        "drift_score",
    ],
)


# ==========================================================
# DERIVED METRICS
# ==========================================================
safe_register(
    DerivedMetric,
    search_fields=[
        "metric_type",
        "sensor__name",
    ],
    filter_fields=[
        "metric_type",
        "sensor",
        "treatment_plant",
        "phase",
    ],
    ordering=[
        "-window_end",
    ],
    select_related=[
        "sensor",
        "treatment_plant",
        "phase",
    ],
    queryset_factory=metric_qs,
)


# ==========================================================
# CALIBRATIONS
# ==========================================================
safe_register(
    InstrumentCalibration,
    search_fields=[
        "instrument__name",
        "instrument__serial_number",
        "performed_by",
        "method",
    ],
    filter_fields=[
        "instrument",
        "valid_until",
    ],
    ordering=[
        "-performed_at",
    ],
    select_related=[
        "instrument",
    ],
    queryset_factory=calibration_qs,
    inline_edit_fields=[
        "valid_until",
        "method",
        "performed_by",
    ],
)


# ==========================================================
# SENSOR HEALTH SNAPSHOTS
# ==========================================================
safe_register(
    SensorHealthSnapshot,
    search_fields=[
        "sensor__name",
        "sensor__parameter__name",
        "reason",
    ],
    filter_fields=[
        "sensor",
        "health_score",
    ],
    ordering=[
        "-assessed_at",
    ],
    select_related=[
        "sensor",
    ],
    queryset_factory=health_qs,
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[instruments.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[instruments.registry] registry unavailable during import"
    )