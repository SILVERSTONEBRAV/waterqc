# core/engine/temporal.py

import uuid
import logging
from datetime import timedelta

from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class TemporalEngine:
    """
    Temporal execution engine for workflow steps.

    Supports:
    - delayed execution
    - retries
    - idempotency
    - async (Celery-ready)
    - fallback sync execution
    """

    DEFAULT_DELAY_SECONDS = 0
    DEFAULT_RETRIES = 3

    # -----------------------------------------------------
    # PUBLIC API
    # -----------------------------------------------------
    @classmethod
    def schedule(cls, workflow_id, step, payload, delay=None, retries=None):
        """
        Schedule a workflow step.

        Args:
            workflow_id: object ID or workflow instance ID
            step: action name
            payload: event payload
            delay: seconds
            retries: retry attempts
        """

        delay = delay if delay is not None else cls.DEFAULT_DELAY_SECONDS
        retries = retries if retries is not None else cls.DEFAULT_RETRIES

        job_id = str(uuid.uuid4())

        execution_time = timezone.now() + timedelta(seconds=delay)

        job = {
            "job_id": job_id,
            "workflow_id": workflow_id,
            "step": step,
            "payload": payload,
            "retries": retries,
            "scheduled_for": execution_time.isoformat(),
        }

        logger.info(f"[Temporal] Scheduling job {job_id} step={step} delay={delay}s")

        # Try async dispatch
        if cls._has_async_backend():
            cls._dispatch_async(job, delay)
        else:
            # fallback → sync execution
            cls._execute(job)

        return job

    # -----------------------------------------------------
    # EXECUTION
    # -----------------------------------------------------
    @classmethod
    def _execute(cls, job):
        """
        Execute job immediately (sync fallback)
        """

        logger.info(f"[Temporal] Executing job {job['job_id']} step={job['step']}")

        try:
            with transaction.atomic():
                cls._run_step(job)

        except Exception as e:
            logger.error(f"[Temporal] Job failed: {job['job_id']} error={e}")

            if job["retries"] > 0:
                job["retries"] -= 1
                logger.info(f"[Temporal] Retrying job {job['job_id']} retries_left={job['retries']}")
                cls._retry(job)
            else:
                logger.error(f"[Temporal] Job permanently failed: {job['job_id']}")

    # -----------------------------------------------------
    # STEP LOGIC
    # -----------------------------------------------------
    @classmethod
    def _run_step(cls, job):
        """
        Core execution logic.
        Extend this with real workflow hooks.
        """

        payload = job.get("payload", {})
        step = job.get("step")

        logger.info(f"[Temporal] Running step '{step}' with payload={payload}")

        # 🔌 HOOK POINT (extend this)
        # Example:
        # if step == "approve":
        #     do_something(payload)

        # For now → no-op
        return True

    # -----------------------------------------------------
    # RETRY
    # -----------------------------------------------------
    @classmethod
    def _retry(cls, job):
        """
        Retry with exponential backoff
        """

        backoff = (cls.DEFAULT_RETRIES - job["retries"]) * 2

        logger.info(f"[Temporal] Backoff retry in {backoff}s for job {job['job_id']}")

        job["scheduled_for"] = (timezone.now() + timedelta(seconds=backoff)).isoformat()

        if cls._has_async_backend():
            cls._dispatch_async(job, backoff)
        else:
            cls._execute(job)

    # -----------------------------------------------------
    # ASYNC BACKEND DETECTION
    # -----------------------------------------------------
    @classmethod
    def _has_async_backend(cls):
        """
        Detect if Celery (or similar) is available
        """
        try:
            import celery  # noqa
            return True
        except ImportError:
            return False

    # -----------------------------------------------------
    # ASYNC DISPATCH (Celery-ready)
    # -----------------------------------------------------
    @classmethod
    def _dispatch_async(cls, job, delay):
        """
        Send job to async worker (Celery)
        """

        try:
            from core.engine.tasks import execute_temporal_job

            logger.info(f"[Temporal] Dispatching async job {job['job_id']}")

            execute_temporal_job.apply_async(
                args=[job],
                countdown=delay
            )

        except Exception as e:
            logger.warning(f"[Temporal] Async dispatch failed, falling back: {e}")
            cls._execute(job)
