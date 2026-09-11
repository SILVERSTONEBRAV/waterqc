# core/engine/ws.py

import json
import logging

logger = logging.getLogger(__name__)


# -----------------------------------------------------
# SAFE CHANNEL LAYER LOADER
# -----------------------------------------------------
def _get_channel_layer():
    try:
        from channels.layers import get_channel_layer
        return get_channel_layer()
    except Exception:
        return None


def _get_async_to_sync():
    try:
        from asgiref.sync import async_to_sync
        return async_to_sync
    except Exception:
        return None


# -----------------------------------------------------
# MAIN API
# -----------------------------------------------------
def broadcast_event(event, group="workflow"):
    """
    Broadcast workflow event to websocket clients.

    Args:
        event: dict or object
        group: channel group
    """

    channel_layer = _get_channel_layer()
    async_to_sync = _get_async_to_sync()

    if not channel_layer or not async_to_sync:
        logger.debug("[WS] Channels not configured, skipping broadcast")
        return False

    try:
        payload = _serialize_event(event)

        async_to_sync(channel_layer.group_send)(
            group,
            {
                "type": "workflow.event",  # maps to consumer method
                "event": payload,
            }
        )

        logger.info(f"[WS] Broadcasted event → group={group}")

        return True

    except Exception as e:
        logger.error(f"[WS] Broadcast failed: {e}")
        return False


# -----------------------------------------------------
# SERIALIZATION
# -----------------------------------------------------
def _serialize_event(event):
    """
    Ensure event is JSON serializable
    """

    if isinstance(event, dict):
        return event

    # try object → dict
    try:
        return {
            "id": getattr(event, "id", None),
            "model": getattr(event, "model", None),
            "action": getattr(event, "action", None),
            "before": getattr(event, "before", None),
            "after": getattr(event, "after", None),
            "timestamp": str(getattr(event, "created_at", "")),
        }
    except Exception:
        return {"raw": str(event)}
