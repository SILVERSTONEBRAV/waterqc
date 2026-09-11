# core/models/workflow_event.py
from django.db import models

class WorkflowEvent(models.Model):
    topic = models.CharField(max_length=100, db_index=True)
    workflow_id = models.CharField(max_length=100, db_index=True)
    model = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    action = models.CharField(max_length=100)

    before = models.CharField(max_length=100, null=True)
    after = models.CharField(max_length=100, null=True)

    payload = models.JSONField()
    idempotency_key = models.CharField(max_length=255, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
