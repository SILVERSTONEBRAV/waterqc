from __future__ import annotations

import logging
import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qad.settings")

logger = logging.getLogger(__name__)

# ==========================================================
# SINGLE SOURCE OF TRUTH CELERY APP
# ==========================================================

app = Celery("qad")

# Load Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# ==========================================================
# STRICT CONFIG OVERRIDES (avoid hidden drift)
# ==========================================================

app.conf.update(
    timezone=getattr(settings, "TIME_ZONE", "Africa/Nairobi"),
    enable_utc=True,

    # Ensure predictable beat behavior
    beat_max_loop_interval=60,

    # Safety defaults for production stability
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# ==========================================================
# TASK DISCOVERY
# ==========================================================

app.autodiscover_tasks()

# ==========================================================
# VALIDATION HOOK (important in your architecture)
# ==========================================================

def validate_celery_app() -> None:
    """
    Ensures Celery app is correctly initialized.
    Prevents silent multi-app drift.
    """
    logger.info("Celery app initialized: %s", app.main)
    logger.info("Broker: %s", app.conf.broker_url)
    logger.info("Timezone: %s", app.conf.timezone)


validate_celery_app()

# ==========================================================
# PUBLIC EXPORT
# ==========================================================

celery = app

__all__ = ("app", "celery")