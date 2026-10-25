"""Transactional outbox for retryable CA dashboard invalidations."""

from __future__ import annotations

import logging
import json
import uuid
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

logger = logging.getLogger(__name__)


def enqueue_ca_event(*, event_type, aggregate_type="chemical", aggregate_id="", payload=None, idempotency_key=None):
    """Persist an event alongside its workflow write and trigger fast delivery."""
    from ca.models import (
        ChemicalAnalysisRequest,
        ChemicalBatch,
        ChemicalOutboxEvent,
        ChecklistForWaterTreatmentChemicalAnalysis,
    )

    payload = dict(payload or {})
    if not payload.get("plant_id"):
        batch_id = payload.get("batch_id")
        if batch_id:
            payload["plant_id"] = (
                ChemicalBatch.objects.filter(pk=batch_id)
                .values_list("treatment_plant_id", flat=True).first()
            )
        elif payload.get("request_id"):
            payload["plant_id"] = (
                ChemicalAnalysisRequest.objects.filter(pk=payload["request_id"])
                .values_list("batch__treatment_plant_id", flat=True).first()
            )
        elif payload.get("checklist_id"):
            payload["plant_id"] = (
                ChecklistForWaterTreatmentChemicalAnalysis.objects.filter(pk=payload["checklist_id"])
                .values_list("chemical_analysis_request__batch__treatment_plant_id", flat=True).first()
            )
    payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
    event, created = ChemicalOutboxEvent.objects.get_or_create(
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        defaults={
            "event_type": str(event_type)[:80],
            "aggregate_type": str(aggregate_type)[:80],
            "aggregate_id": str(aggregate_id)[:80],
            "payload": payload or {},
        },
    )
    if created:
        def dispatch():
            try:
                from ca.tasks import publish_ca_outbox_events
                publish_ca_outbox_events.delay()
            except Exception:
                logger.info("CA outbox event %s will be retried by the scheduled dispatcher", event.event_id)

        transaction.on_commit(dispatch)
    return event
