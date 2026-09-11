from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from multiprocessing import cpu_count
from threading import Lock
from typing import Any

from celery import Celery
from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    task_success,
    worker_ready,
)
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qad.settings")

logger = logging.getLogger(__name__)

# ==============================================================================
# CELERY APPLICATION
# ==============================================================================

app = Celery("qad")

app.config_from_object("django.conf:settings", namespace="CELERY")


def _worker_concurrency() -> int:
    """
    Safe worker concurrency.

    Honors CELERY_WORKER_CONCURRENCY if supplied,
    otherwise limits automatic concurrency to avoid
    oversubscribing small containers.
    """
    env = os.getenv("CELERY_WORKER_CONCURRENCY")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass

    return max(2, min(cpu_count(), 8))


app.conf.update(
    broker_url=getattr(settings, "CELERY_BROKER_URL"),
    result_backend=getattr(settings, "CELERY_RESULT_BACKEND"),
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    timezone=getattr(settings, "TIME_ZONE", "Africa/Nairobi"),
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=getattr(
        settings,
        "CELERY_WORKER_PREFETCH_MULTIPLIER",
        1,
    ),
    worker_concurrency=_worker_concurrency(),
    worker_max_tasks_per_child=getattr(
        settings,
        "CELERY_WORKER_MAX_TASKS_PER_CHILD",
        1000,
    ),
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_time_limit=getattr(
        settings,
        "CELERY_TASK_TIME_LIMIT",
        1800,
    ),
    task_soft_time_limit=getattr(
        settings,
        "CELERY_TASK_SOFT_TIME_LIMIT",
        1500,
    ),
    result_expires=getattr(
        settings,
        "CELERY_RESULT_EXPIRES",
        3600,
    ),
    beat_scheduler=getattr(
        settings,
        "CELERY_BEAT_SCHEDULER",
        "django_celery_beat.schedulers:DatabaseScheduler",
    ),
    beat_max_loop_interval=getattr(
        settings,
        "CELERY_BEAT_MAX_LOOP_INTERVAL",
        60,
    ),
)

# ==============================================================================
# TASK DISCOVERY
# ==============================================================================

app.autodiscover_tasks()

logger.info(
    "Celery autodiscovered tasks using DatabaseScheduler."
)

# ==============================================================================
# METRICS
# ==============================================================================

_metrics_lock = Lock()

_running_tasks: dict[str, float] = {}

task_metrics: defaultdict[str, dict[str, Any]] = defaultdict(
    lambda: {
        "count": 0,
        "success": 0,
        "failure": 0,
        "avg_runtime": 0.0,
        "max_runtime": 0.0,
    }
)


def reset_metrics() -> None:
    global _running_tasks
    global task_metrics

    with _metrics_lock:
        _running_tasks = {}

        task_metrics = defaultdict(
            lambda: {
                "count": 0,
                "success": 0,
                "failure": 0,
                "avg_runtime": 0.0,
                "max_runtime": 0.0,
            }
        )


def record_runtime(
    task_name: str,
    task_id: str,
) -> float | None:
    with _metrics_lock:
        started = _running_tasks.pop(task_id, None)

    if started is None:
        return None

    runtime = time.perf_counter() - started

    metrics = task_metrics[task_name]

    completed = (
        metrics["success"]
        + metrics["failure"]
        + 1
    )

    metrics["avg_runtime"] = (
        (
            metrics["avg_runtime"]
            * (completed - 1)
        )
        + runtime
    ) / completed

    metrics["max_runtime"] = max(
        metrics["max_runtime"],
        runtime,
    )

    return runtime


# ==============================================================================
# SIGNALS
# ==============================================================================


@task_prerun.connect
def on_task_prerun(
    sender=None,
    task_id=None,
    **kwargs,
):
    if not sender or not task_id:
        return

    with _metrics_lock:
        _running_tasks[task_id] = time.perf_counter()

    task_metrics[sender.name]["count"] += 1


@task_success.connect
def on_task_success(
    sender=None,
    **kwargs,
):
    if not sender:
        return

    request = getattr(sender, "request", None)
    task_id = getattr(request, "id", None)

    task_metrics[sender.name]["success"] += 1

    if task_id:
        record_runtime(sender.name, task_id)


@task_failure.connect
def on_task_failure(
    sender=None,
    task_id=None,
    **kwargs,
):
    if not sender:
        return

    task_metrics[sender.name]["failure"] += 1

    if task_id:
        record_runtime(sender.name, task_id)


@task_postrun.connect
def on_task_postrun(
    task_id=None,
    **kwargs,
):
    if task_id:
        with _metrics_lock:
            _running_tasks.pop(task_id, None)


@worker_ready.connect
def on_worker_ready(**kwargs):
    reset_metrics()

    logger.info(
        "Celery worker ready."
    )


# ==============================================================================
# INTERNAL TASKS
# ==============================================================================


@app.task(name="qad.celery.aggregate_celery_metrics")
def aggregate_celery_metrics():
    return {
        name: {
            "runs": m["count"],
            "success": m["success"],
            "failure": m["failure"],
            "avg_runtime": round(
                m["avg_runtime"],
                3,
            ),
            "max_runtime": round(
                m["max_runtime"],
                3,
            ),
        }
        for name, m in task_metrics.items()
    }


@app.task(bind=True, name="qad.debug_task")
def debug_task(self):
    request = self.request

    return {
        "id": request.id,
        "task": request.task,
        "hostname": request.hostname,
    }


# ==============================================================================
# INITIALIZATION
# ==============================================================================


def initialize() -> None:
    logger.info("=" * 72)
    logger.info("Celery initialized")
    logger.info("Broker      : %s", app.conf.broker_url)
    logger.info("Backend     : %s", app.conf.result_backend)
    logger.info("Scheduler   : %s", app.conf.beat_scheduler)
    logger.info("Timezone    : %s", app.conf.timezone)
    logger.info("=" * 72)


celery = app

__all__ = (
    "app",
    "celery",
    "aggregate_celery_metrics",
    "debug_task",
    "initialize",
)