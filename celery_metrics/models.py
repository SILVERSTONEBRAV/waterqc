# celery_metrics/models.py
import uuid
import logging
import asyncio
from django.db import models
from django.utils import timezone
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

class CeleryTaskMetric(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    status = models.CharField(
        max_length=50,
        choices=[
            ("SUCCESS", "SUCCESS"),
            ("FAILURE", "FAILURE"),
            ("STARTED", "STARTED"),
            ("RETRY", "RETRY"),
        ],
        default="STARTED",
    )
    runtime = models.FloatField(default=0.0)
    timestamp = models.DateTimeField(default=timezone.now)
    worker = models.CharField(max_length=255, blank=True, null=True)
    result = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["name", "timestamp"])]

    def __str__(self):
        return f"{self.name} ({self.status})"

    @classmethod
    async def arecord(cls, name: str, status: str, runtime: float, result=None, worker=None):
        obj = await sync_to_async(cls.objects.create)(
            name=name,
            status=status,
            runtime=runtime,
            result=result or {},
            worker=worker,
        )
        layer = get_channel_layer()
        if not layer:
            logger.warning("No channel layer available — skipping metrics broadcast.")
            return obj

        payload = {
            "type": "metrics.update",
            "data": {
                "task": name,
                "status": status,
                "runtime": runtime,
                "timestamp": obj.timestamp.isoformat(),
            },
        }
        try:
            await asyncio.wait_for(layer.group_send("celery_metrics", payload), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("WebSocket metrics broadcast timed out — skipping.")
        except Exception as e:
            logger.exception(f"Failed to broadcast Celery metric: {e}")

        return obj

    @classmethod
    def record(cls, name: str, status: str, runtime: float, result=None, worker=None):
        try:
            asyncio.get_running_loop()
            return asyncio.create_task(cls.arecord(name, status, runtime, result, worker))
        except RuntimeError:
            return asyncio.run(cls.arecord(name, status, runtime, result, worker))
