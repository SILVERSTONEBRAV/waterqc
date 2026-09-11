from __future__ import annotations

import logging
import time

from celery import shared_task
from django.utils import timezone

from qc.services.analysis_generator import AnalysisGenerator


logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="qc.generate_due_analyses",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def generate_due_analyses_task(
    self,
    force: bool = False,
    plant_ids: list[int] | None = None,
    backfill_minutes: int = 5,
):
    """
    Automatic QC analysis generation.

    Runs every minute via django-celery-beat.
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
            "[QC] Analysis generation failed"
        )

        raise



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