# qc/signals.py

import logging
from datetime import datetime

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models.signals import post_migrate, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger("qc.signals")


# ============================================================
# Bootstrap QC Sampling Schedules & Periodic Tasks
# ============================================================

@receiver(post_migrate, dispatch_uid="qc.bootstrap_sampling_system")
def bootstrap_sampling_system(sender, **kwargs):
    """
    Create default sampling schedules and periodic task after migrations.
    Safe to run multiple times.
    """

    if sender.label != "qc":
        return

    try:
        Schedule = apps.get_model("qc", "SamplingSchedule")
        TreatmentPlant = apps.get_model("t", "TreatmentPlant")
    except LookupError:
        return

    table_names = connection.introspection.table_names()

    if Schedule._meta.db_table not in table_names:
        return

    # Ensure periodic task for celery-beat
    try:
        from django_celery_beat.models import PeriodicTask, IntervalSchedule
        interval, _ = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.MINUTES,
        )
        PeriodicTask.objects.get_or_create(
            name="qc.generate_due_analyses",
            defaults={
                "task": "qc.generate_due_analyses",
                "interval": interval,
                "enabled": True,
            },
        )
    except Exception as exc:
        logger.warning("Could not register PeriodicTask in beat: %s", exc)

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

    plants = TreatmentPlant.objects.all()
    for plant in plants:
        for item in defaults:
            data = dict(item)
            data["treatment_plant"] = plant
            schedule, created = Schedule.objects.get_or_create(
                treatment_plant=plant,
                water_type=item["water_type"],
                defaults=data,
            )

            if created:
                logger.info(
                    "Created default schedule for %s plant=%s",
                    schedule.water_type,
                    plant.name,
                )

            if schedule.enabled and schedule.sampling_times.count() == 0:
                try:
                    schedule.generate_times()
                except Exception:
                    logger.exception(
                        "Failed generating sampling times for %s plant=%s",
                        schedule.water_type,
                        plant.name,
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
    if not instance.reference_id:
        if hasattr(instance, "generate_reference"):
            instance.reference_id = instance.generate_reference()


# ============================================================
# Prevent Duplicate Analysis
# ============================================================

@receiver(
    pre_save,
    sender=apps.get_model("qc", "WaterAnalysis"),
    dispatch_uid="qc.unique_analysis",
)
def enforce_unique_analysis_time(sender, instance, **kwargs):
    if not instance.analysis_time or not instance.treatment_plant:
        return

    water_type = getattr(instance.analysis_time, "water_type", None) or "Water"

    existing = sender.objects.filter(
        treatment_plant=instance.treatment_plant,
        analysis_date=instance.analysis_date,
        analysis_time=instance.analysis_time,
    ).exclude(pk=instance.pk)

    if existing.exists():
        raise ValidationError(
            f"{water_type.title()} analysis for "
            f"{instance.analysis_time.time.strftime('%I:%M %p')} on {instance.analysis_date} "
            f"already exists."
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

    from qc.services.result_generator import AnalysisResultGenerator
    try:
        AnalysisResultGenerator.generate_for_analysis(instance)
    except Exception:
        logger.exception(
            "Failed generating results for analysis=%s",
            instance.pk,
        )