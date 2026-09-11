# core/workflow/event_store.py

from django.db import models
from django.utils import timezone


class WorkflowEvent(models.Model):
    """
    Event-sourced workflow ledger.
    Everything becomes an immutable event.
    """

    model_key = models.CharField(max_length=255, db_index=True)
    object_id = models.CharField(max_length=255, db_index=True)

    action = models.CharField(max_length=255)
    from_state = models.CharField(max_length=255, null=True, blank=True)
    to_state = models.CharField(max_length=255, null=True, blank=True)

    payload = models.JSONField(default=dict)

    user_id = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["model_key", "object_id"]),
            models.Index(fields=["created_at"]),
        ]
