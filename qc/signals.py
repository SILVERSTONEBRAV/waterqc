# qc/signals.py

import logging
from datetime import datetime

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models.signals import post_delete, post_migrate, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger("qc.signals")


def _sync_result_nonconformity(sender, instance, **kwargs):
    """Keep a QC nonconformity in sync whenever a water result is saved."""
    from qc.models import (
        NonConformity,
        NonConformityLog,
        NonConformityStatus,
    )

    if instance.value is None or not instance.parameter_id:
        return

    limit = instance.parameter
    if limit.min_value is None and limit.max_value is None:
        return

    observed = float(instance.value)
    minimum = float(limit.min_value) if limit.min_value is not None else None
    maximum = float(limit.max_value) if limit.max_value is not None else None
    below = minimum is not None and observed < minimum
    above = maximum is not None and observed > maximum

    parameter_name = str(limit.parameter)
    if instance.phase_id:
        parameter_name = f"{parameter_name} ({instance.phase.name})"

    existing = NonConformity.objects.filter(
        analysis_id=instance.analysis_id,
        parameter_name=parameter_name,
        status__in=(NonConformityStatus.OPEN, NonConformityStatus.UNDER_REVIEW),
    )
    if not below and not above:
        for nc in existing:
            nc.close(remarks=f"Value {observed} returned within the configured limits.")
        return

    # The legacy model requires numeric bounds; use the observed edge where a
    # limit is intentionally unbounded, while keeping deviation meaningful.
    min_value = minimum if minimum is not None else observed
    max_value = maximum if maximum is not None else observed
    deviation = (minimum - observed) if below else (observed - maximum)
    nc = existing.order_by("-created_at").first()
    created = nc is None
    if created:
        nc = NonConformity.objects.create(
            analysis_id=instance.analysis_id,
            parameter_name=parameter_name,
            observed_value=observed,
            min_limit=min_value,
            max_limit=max_value,
            deviation=deviation,
            triggered_by=None,
            auto_detected=True,
        )
        nc.evaluate_risk()
        NonConformityLog.objects.create(
            nonconformity=nc,
            action="auto_detected",
            remarks=(
                f"Detected water result {observed}; allowed range is "
                f"{minimum if minimum is not None else 'unbounded'} to "
                f"{maximum if maximum is not None else 'unbounded'}."
            ),
            auto_generated=True,
        )
        transaction.on_commit(lambda: _broadcast_nonconformity(nc))
    elif (nc.observed_value, nc.min_limit, nc.max_limit, nc.deviation) != (
        observed, min_value, max_value, deviation
    ):
        nc.observed_value = observed
        nc.min_limit = min_value
        nc.max_limit = max_value
        nc.deviation = deviation
        nc.save(update_fields=["observed_value", "min_limit", "max_limit", "deviation", "updated_at"])


def _broadcast_nonconformity(nc):
    """Push a new QC nonconformity directly into the live alerts stream."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        message = (
            f"Water quality nonconformity: {nc.parameter_name} measured "
            f"{nc.observed_value} (allowed {nc.min_limit}–{nc.max_limit})."
        )
        async_to_sync(channel_layer.group_send)(
            "alerts_stream",
            {
                "type": "alert.message",
                "message": message,
                "priority": "high",
                "alert_type": "nonconformity",
                "instance_ref": f"NC-{nc.pk}",
            },
        )
        async_to_sync(channel_layer.group_send)(
            f"qc-plant-{nc.analysis.treatment_plant_id}",
            {
                "type": "qc_nonconformity_created",
                "nonconformity_id": nc.pk,
                "analysis_id": nc.analysis_id,
                "plant_id": nc.analysis.treatment_plant_id,
                "parameter_name": nc.parameter_name,
                "observed_value": nc.observed_value,
                "min_limit": nc.min_limit,
                "max_limit": nc.max_limit,
                "timestamp": timezone.now().isoformat(),
            },
        )
    except Exception:
        logger.exception("Failed broadcasting QC nonconformity alert nc=%s", nc.pk)


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
            "adaptive": False,
        },
        {
            "water_type": "treated",
            "start_time": datetime.strptime("00:00", "%H:%M").time(),
            "interval_minutes": 30,
            "adaptive": False,
        },
        {
            "water_type": "coagulated",
            "start_time": datetime.strptime("02:00", "%H:%M").time(),
            "interval_minutes": 120,
            "adaptive": False,
        },
        {
            "water_type": "clarified",
            "start_time": datetime.strptime("00:30", "%H:%M").time(),
            "interval_minutes": 120,
            "adaptive": False,
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
        AnalysisResultGenerator.generate_for_analysis(instance, emit_change=False)
    except Exception:
        logger.exception(
            "Failed generating results for analysis=%s",
            instance.pk,
        )


@receiver(
    post_save,
    sender=apps.get_model("qc", "WaterAnalysis"),
    dispatch_uid="qc.enqueue_analysis_change",
)
def enqueue_analysis_change(sender, instance, created, **kwargs):
    """Persist one refresh event after the analysis and result generation save."""
    if not instance.treatment_plant_id:
        return

    try:
        water_type = instance.water_type
    except Exception:
        water_type = ""

    from qc.services.realtime_outbox import enqueue_qc_results_changed

    enqueue_qc_results_changed(
        analysis_id=instance.pk,
        plant_id=instance.treatment_plant_id,
        water_type=water_type,
        action="created" if created else "updated",
        changed_model="wateranalysis",
    )


@receiver(
    post_delete,
    sender=apps.get_model("qc", "WaterAnalysis"),
    dispatch_uid="qc.enqueue_analysis_delete",
)
def enqueue_analysis_delete(sender, instance, **kwargs):
    if not instance.treatment_plant_id:
        return
    try:
        water_type = instance.water_type
    except Exception:
        water_type = ""
    from qc.services.realtime_outbox import enqueue_qc_results_changed

    enqueue_qc_results_changed(
        analysis_id=instance.pk,
        plant_id=instance.treatment_plant_id,
        water_type=water_type,
        action="deleted",
        changed_model="wateranalysis",
    )


def enqueue_result_change(sender, instance, created=False, **kwargs):
    analysis = instance.analysis
    from qc.services.realtime_outbox import enqueue_qc_results_changed

    enqueue_qc_results_changed(
        analysis_id=instance.analysis_id,
        plant_id=analysis.treatment_plant_id,
        water_type=analysis.water_type,
        action="created" if created else "updated",
        changed_model=sender._meta.model_name,
    )


def enqueue_result_delete(sender, instance, origin=None, **kwargs):
    origin_model = getattr(origin, "model", origin.__class__ if origin is not None else None)
    if origin_model is apps.get_model("qc", "WaterAnalysis"):
        # The parent analysis delete event below already invalidates its cards.
        return

    from qc.models import WaterAnalysis

    analysis = WaterAnalysis.objects.filter(pk=instance.analysis_id).first()
    if analysis is None:
        return
    from qc.services.realtime_outbox import enqueue_qc_results_changed

    enqueue_qc_results_changed(
        analysis_id=instance.analysis_id,
        plant_id=analysis.treatment_plant_id,
        water_type=analysis.water_type,
        action="deleted",
        changed_model=sender._meta.model_name,
    )


# Result values can be entered through the worksheet, API, instruments, or
# admin. A model signal keeps the QC finding workflow consistent across them.
for _result_model_name in (
    "RawWaterResult",
    "TreatedWaterResult",
    "CoagulatedWaterResult",
    "ClarifiedWaterResult",
):
    post_save.connect(
        _sync_result_nonconformity,
        sender=apps.get_model("qc", _result_model_name),
        dispatch_uid=f"qc.auto_nonconformity.{_result_model_name.lower()}",
    )
    post_save.connect(
        enqueue_result_change,
        sender=apps.get_model("qc", _result_model_name),
        weak=False,
        dispatch_uid=f"qc.enqueue_result_change.{_result_model_name.lower()}",
    )
    post_delete.connect(
        enqueue_result_delete,
        sender=apps.get_model("qc", _result_model_name),
        weak=False,
        dispatch_uid=f"qc.enqueue_result_delete.{_result_model_name.lower()}",
    )
