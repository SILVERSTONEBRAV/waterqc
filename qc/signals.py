# qc/signals.py

import logging
from datetime import datetime, timedelta

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models.signals import post_migrate, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger("qc.signals")


# ============================================================
# Deferred Alert Engine Import
# ============================================================

def get_alert_engine():
    """Lazy import to avoid circular imports."""
    from alerts.engine import AlertEngine
    return AlertEngine


# ============================================================
# Bootstrap QC Sampling Schedules
# ============================================================

@receiver(post_migrate, dispatch_uid="qc.bootstrap_sampling_system")
def bootstrap_sampling_system(sender, **kwargs):
    """
    Create default sampling schedules after migrations.

    Safe to run multiple times.
    """

    if sender.label != "qc":
        return

    try:
        Schedule = apps.get_model("qc", "SamplingSchedule")
    except LookupError:
        return

    table_names = connection.introspection.table_names()

    if Schedule._meta.db_table not in table_names:
        return

    defaults = [
        {
            "water_type": "raw",
            "start_time": datetime.strptime("00:00", "%H:%M").time(),
            "interval_minutes": 30,
        },
        {
            "water_type": "treated",
            "start_time": datetime.strptime("00:00", "%H:%M").time(),
            "interval_minutes": 30,
        },
        {
            "water_type": "coagulated",
            "start_time": datetime.strptime("02:00", "%H:%M").time(),
            "interval_minutes": 120,
        },
        {
            "water_type": "clarified",
            "start_time": datetime.strptime("00:30", "%H:%M").time(),
            "interval_minutes": 120,
        },
    ]

    for item in defaults:

        schedule, created = Schedule.objects.get_or_create(
            water_type=item["water_type"],
            defaults=item,
        )

        if created:
            logger.info(
                "Created default schedule for %s",
                schedule.water_type,
            )

    for schedule in Schedule.objects.filter(enabled=True):

        try:
            schedule.generate_times()

        except Exception:
            logger.exception(
                "Failed generating sampling times for %s",
                schedule.water_type,
            )


# ============================================================
# Generate Reference ID
# ============================================================

@receiver(
    pre_save,
    sender=apps.get_model("qc", "WaterAnalysis"),
    dispatch_uid="qc.reference_id",
)
def ensure_reference_id(sender, instance, **kwargs):

    if instance.reference_id:
        return

    if hasattr(sender, "generate_reference_id"):

        for _ in range(50):

            ref = sender.generate_reference_id()

            if not sender.objects.filter(reference_id=ref).exists():
                instance.reference_id = ref
                return

    raise ValueError("Unable to generate unique reference ID.")


# ============================================================
# Prevent Duplicate Analysis
# ============================================================

@receiver(
    pre_save,
    sender=apps.get_model("qc", "WaterAnalysis"),
    dispatch_uid="qc.unique_analysis",
)
def enforce_unique_analysis_time(sender, instance, **kwargs):

    if not instance.analysis_time:
        return

    water_type = getattr(instance.analysis_time, "water_type", None)

    if not water_type:
        return

    since = timezone.now() - timedelta(hours=24)

    existing = sender.objects.filter(
        analysis_time=instance.analysis_time,
        created_at__gte=since,
    ).exclude(pk=instance.pk)

    if existing.exists():

        raise ValidationError(
            f"{water_type.title()} analysis for "
            f"{instance.analysis_time.time.strftime('%I:%M %p')} "
            f"already exists within the last 24 hours."
        )


# ============================================================
# Auto Create Parameter Results
# ============================================================

@receiver(
    post_save,
    sender=apps.get_model("qc", "WaterAnalysis"),
    dispatch_uid="qc.populate_results",
)
def auto_populate_results(sender, instance, created, **kwargs):

    if not created:
        return

    if not instance.analysis_time:
        return

    water_type = getattr(instance.analysis_time, "water_type", None)

    mapping = {

        "raw": (
            "RawWaterResult",
            "RawWaterLimit",
        ),

        "treated": (
            "TreatedWaterResult",
            "TreatedWaterLimit",
        ),

        "coagulated": (
            "CoagulatedWaterResult",
            "CoagulatedWaterLimit",
        ),

        "clarified": (
            "ClarifiedWaterResult",
            "ClarifiedWaterLimit",
        ),

    }

    if water_type not in mapping:
        return

    result_name, limit_name = mapping[water_type]

    try:

        ResultModel = apps.get_model("qc", result_name)

        LimitModel = apps.get_model("t", limit_name)

    except LookupError:

        logger.exception(
            "Unable to load models for %s",
            water_type,
        )

        return

    limits = LimitModel.objects.all()

    if not limits.exists():

        logger.warning(
            "No limits configured for %s water",
            water_type,
        )

        return

    with transaction.atomic():

        for parameter in limits:

            ResultModel.objects.get_or_create(

                analysis=instance,

                parameter=parameter,

                defaults={

                    "value": None,

                    # replace with your default state if required
                    "state": getattr(
                        ResultModel,
                        "DEFAULT_STATE",
                        "pending",
                    ),

                },

            )

    logger.info(
        "%s parameter results generated.",
        water_type.title(),
    )