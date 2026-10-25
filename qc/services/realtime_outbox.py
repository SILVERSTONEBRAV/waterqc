"""Durable delivery of plant-scoped QC result refresh events."""

from __future__ import annotations

import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_CLAIM_SECONDS = 30
_RETRY_BASE_SECONDS = 5
_RETRY_MAX_SECONDS = 300


def enqueue_qc_results_changed(
    *,
    analysis_id,
    plant_id,
    water_type="",
    action="updated",
    changed_model="wateranalysis",
):
    """Write an invalidation event in the same transaction as its QC change."""
    from qc.models import QCRealtimeOutboxEvent

    event = QCRealtimeOutboxEvent.objects.create(
        event_type="qc.results.changed",
        aggregate_type="water_analysis",
        aggregate_id=str(analysis_id),
        plant_id=int(plant_id),
        payload={
            "analysis_id": str(analysis_id),
            "water_type": str(water_type or ""),
            "action": str(action or "updated"),
            "changed_model": str(changed_model or "")[:80],
        },
    )
    transaction.on_commit(
        lambda event_id=event.event_id: publish_qc_outbox_event(event_id),
        using=event._state.db,
    )
    return event


def publish_qc_outbox_event(event_id):
    """Claim and publish one event; failures remain queued for retry."""
    from qc.models import QCRealtimeOutboxEvent

    now = timezone.now()
    with transaction.atomic():
        event = (
            QCRealtimeOutboxEvent.objects.select_for_update()
            .filter(
                event_id=event_id,
                delivered_at__isnull=True,
                available_at__lte=now,
            )
            .first()
        )
        if event is None:
            return False

        event.attempt_count += 1
        attempt = event.attempt_count
        event.available_at = now + timedelta(seconds=_CLAIM_SECONDS)
        event.save(update_fields=("attempt_count", "available_at"))
        payload = dict(event.payload or {})
        plant_id = event.plant_id
        event_id = str(event.event_id)
        created_at = event.created_at.isoformat()

    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            raise RuntimeError("No Channels layer is configured for QC events.")

        message = {
            "type": "qc_results_changed",
            "event_id": event_id,
            "event_type": "qc.results.changed",
            "plant_id": plant_id,
            "timestamp": created_at,
            **payload,
        }
        async_to_sync(channel_layer.group_send)(f"qc-plant-{plant_id}", message)
        # The global group is joined only by authenticated superusers.
        async_to_sync(channel_layer.group_send)("qc-dashboard", message)

        QCRealtimeOutboxEvent.objects.filter(
            event_id=event_id,
            delivered_at__isnull=True,
        ).update(delivered_at=timezone.now(), last_error="")
        return True
    except Exception as exc:
        delay = min(
            _RETRY_BASE_SECONDS * (2 ** min(attempt - 1, 6)),
            _RETRY_MAX_SECONDS,
        )
        QCRealtimeOutboxEvent.objects.filter(
            event_id=event_id,
            delivered_at__isnull=True,
        ).update(
            available_at=timezone.now() + timedelta(seconds=delay),
            last_error=str(exc)[:4000],
        )
        logger.exception("QC outbox event %s failed; retrying in %ss", event_id, delay)
        return False


def publish_pending_qc_events(batch_size=200):
    """Retry committed outbox events missed by the immediate post-commit send."""
    from qc.models import QCRealtimeOutboxEvent

    now = timezone.now()
    event_ids = list(
        QCRealtimeOutboxEvent.objects.filter(
            delivered_at__isnull=True,
            available_at__lte=now,
        )
        .order_by("created_at", "event_id")
        .values_list("event_id", flat=True)[: max(1, min(int(batch_size), 1000))]
    )
    delivered = sum(publish_qc_outbox_event(event_id) for event_id in event_ids)
    return {"claimed": len(event_ids), "delivered": delivered}
