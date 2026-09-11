# wsp/models_metrics.py
import uuid
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from channels.layers import get_channel_layer


class CeleryTaskMetric(models.Model):
    STATUS_CHOICES = [
        ("SUCCESS", "SUCCESS"),
        ("FAILURE", "FAILURE"),
        ("STARTED", "STARTED"),
        ("RETRY", "RETRY"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="STARTED")
    runtime = models.FloatField(default=0.0)
    timestamp = models.DateTimeField(default=timezone.now)
    worker = models.CharField(max_length=255, blank=True, null=True, default="unknown")
    result = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["name", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.status})"

    @classmethod
    async def record_async(
        cls, name: str, status: str, runtime: float, result=None, worker=None
    ):
        # Validate status
        if status not in dict(cls.STATUS_CHOICES):
            raise ValidationError(f"Invalid status: {status}")

        # Create the metric asynchronously
        obj = await cls.objects.acreate(
            name=name,
            status=status,
            runtime=runtime,
            result=result or {},
            worker=worker or "unknown",
        )

        # Send update over WebSocket
        layer = get_channel_layer()
        if layer:
            try:
                await layer.group_send(
                    "celery_metrics",
                    {
                        "type": "metrics_update",
                        "data": {
                            "task": name,
                            "status": status,
                            "runtime": runtime,
                            "timestamp": obj.timestamp.isoformat(),
                        },
                    },
                )
            except Exception as e:
                # Optional: log the error instead of failing
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"WebSocket send failed: {e}")

        return obj
