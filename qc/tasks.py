from __future__ import annotations

import logging
import time
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from qc.services.analysis_generator import AnalysisGenerator


logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="qc.generate_due_analyses",
    ignore_result=True,
)
def generate_due_analyses_task(
    self,
    force: bool = False,
    plant_ids: list[int] | None = None,
    backfill_minutes: int = 30,
):
    """
    Automatic QC analysis generation.

    Runs every minute via django-celery-beat perpetually (10+ years 24/7).
    Searches current and recently missed sampling windows.
    """

    started = timezone.localtime()
    timer = time.monotonic()

    logger.info(
        "[QC] Analysis generation started | %s",
        started.isoformat(),
    )

    try:

        result = AnalysisGenerator.generate_due_analyses(
            force=force,
            plant_ids=plant_ids,
            backfill_minutes=backfill_minutes,
        )

        elapsed = time.monotonic() - timer

        logger.info(
            "[QC] Analysis generation completed | "
            "Created=%s Existing=%s Errors=%s Skipped=%s Duration=%.2fs",
            result.get("created", 0),
            result.get("existing", 0),
            result.get("errors", 0),
            result.get("skipped", False),
            elapsed,
        )

        return result

    except Exception:

        logger.exception(
            "[QC] Analysis generation encountered an error; will auto-resume on next minute interval"
        )

        return {"errors": 1, "success": False}



@shared_task(
    bind=True,
    name="qc.generate_analysis_now",
)
def generate_analysis_now(
    self,
    plant_ids: list[int] | None = None,
    backfill_minutes: int = 60,
):
    """
    Manual QC analysis generation.

    Bypasses distributed cache locking.
    Useful for repair/testing.
    """

    logger.info(
        "[QC] Manual analysis generation requested"
    )


    return AnalysisGenerator.generate_due_analyses(
        force=True,
        plant_ids=plant_ids,
        backfill_minutes=backfill_minutes,
    )



@shared_task(
    bind=True,
    name="qc.health_check",
)
def qc_health_check(self):

    return {
        "status": "healthy",
        "worker": self.request.hostname,
        "timestamp": timezone.now().isoformat(),
    }


@shared_task(name="qc.publish_qc_outbox_events", ignore_result=True)
def publish_qc_outbox_events(batch_size=200):
    """Retry durable QC events if a web process stopped after database commit."""
    from qc.services.realtime_outbox import publish_pending_qc_events

    return publish_pending_qc_events(batch_size=batch_size)


@shared_task(name="qc.prune_qc_outbox_events", ignore_result=True)
def prune_qc_outbox_events(retention_days=30, batch_size=5000):
    """Bound delivered-event storage while retaining pending events indefinitely."""
    from qc.models import QCRealtimeOutboxEvent

    cutoff = timezone.now() - timedelta(days=max(1, int(retention_days)))
    event_ids = list(
        QCRealtimeOutboxEvent.objects.filter(delivered_at__lt=cutoff)
        .order_by("delivered_at")
        .values_list("event_id", flat=True)[: max(1, min(int(batch_size), 10000))]
    )
    deleted, _ = QCRealtimeOutboxEvent.objects.filter(
        event_id__in=event_ids,
        delivered_at__lt=cutoff,
    ).delete()
    logger.info("Pruned %s delivered QC outbox events older than %s days", deleted, retention_days)
    return {"deleted": deleted}
