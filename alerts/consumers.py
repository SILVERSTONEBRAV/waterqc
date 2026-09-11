#alerts/consumers.py
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from alerts.models import (
    AlertState,
    AlarmAcknowledgment,
)
from alerts.utils import generate_voice_notification_pyttsx3

logger = logging.getLogger(__name__)


class AlertConsumer(AsyncWebsocketConsumer):
    """
    Advanced WebSocket consumer for alerts & alarm streams.

    ✅ Model-aligned with alerts.models
    ✅ Supports:
        - GenericForeignKey acknowledgments
        - Alert state updates
        - Voice + alarm signaling
        - Geo/AI enriched payloads
        - Per-user + global streams
    """

    # --------------------------------------------------
    #  CONNECT / DISCONNECT
    # --------------------------------------------------
    async def connect(self):
        user = self.scope.get("user")
        self.user = user if user and user.is_authenticated else None

        self.global_group = "alerts_stream"
        self.user_group = f"user_{self.user.id}_alerts" if self.user else None

        try:
            await self.channel_layer.group_add(self.global_group, self.channel_name)
            if self.user_group:
                await self.channel_layer.group_add(self.user_group, self.channel_name)

            await self.accept()
            logger.info(f"✅ Alert WS connected → {self.channel_name}")

        except Exception:
            logger.exception("❌ WebSocket connection failure")
            await self.close(code=1011)

    async def disconnect(self, close_code):
        try:
            await self.channel_layer.group_discard(self.global_group, self.channel_name)
            if self.user_group:
                await self.channel_layer.group_discard(self.user_group, self.channel_name)
        except Exception:
            logger.exception("⚠️ WS disconnect cleanup failed")


    # --------------------------------------------------
    #  RECEIVE FROM CLIENT
    # --------------------------------------------------
    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            payload = json.loads(text_data)
            msg_type = payload.get("type")

            if msg_type == "acknowledge":
                await self._acknowledge_alert(payload)

            elif msg_type == "ping":
                await self.send_json({"type": "pong"})

            else:
                logger.warning(f"⚠️ Unknown WS message type: {msg_type}")

        except json.JSONDecodeError:
            await self.send_json({"error": "Invalid JSON"})
        except Exception:
            logger.exception("❌ WS receive error")
            await self.send_json({"error": "Server error"})


    # --------------------------------------------------
    #  EVENTS FROM CHANNEL LAYER
    # --------------------------------------------------
    async def alert_message(self, event):
        """Primary alert dispatch."""
        await self.send_json({
            "type": "alert",
            "message": event.get("message"),
            "priority": event.get("priority"),
            "alert_type": event.get("alert_type"),
            "instance_ref": event.get("instance_ref"),
            "geo": event.get("geo"),
            "timestamp": timezone.now().isoformat()
        })

        if self.user:
            await self._trigger_alarm(event.get("message"))


    async def alert_state(self, event):
        """State transition push."""
        await self.send_json({
            "type": "state_change",
            "state": event.get("message"),
            "geo": event.get("geo"),
            "timestamp": timezone.now().isoformat()
        })


    # --------------------------------------------------
    #  ACKNOWLEDGMENT LOGIC (MODEL-CORRECT)
    # --------------------------------------------------
    async def _acknowledge_alert(self, payload):
        """
        Persist acknowledgment using GenericForeignKey.

        Payload:
        {
            type: "acknowledge",
            content_type: "nonconformity",
            object_id: 123
        }
        """
        if not self.user:
            return

        model_name = payload.get("content_type")
        object_id = payload.get("object_id")

        if not model_name or not object_id:
            return

        try:
            ct = await database_sync_to_async(ContentType.objects.get)(
                model=model_name
            )

            await database_sync_to_async(AlarmAcknowledgment.objects.update_or_create)(
                user=self.user,
                content_type=ct,
                object_id=object_id,
                defaults={
                    "acknowledged": True,
                    "acknowledged_at": timezone.now(),
                },
            )

            # Update alert state if exists
            await database_sync_to_async(
                AlertState.objects.filter(
                    instance_ref=str(object_id)
                ).update
            )(state=AlertState.StateChoices.ACKNOWLEDGED)

            await self.send_json({
                "type": "ack",
                "status": "ok",
                "object_id": object_id
            })

            logger.info(f"✅ Alert acknowledged by user={self.user.id} obj={object_id}")

        except ContentType.DoesNotExist:
            logger.warning(f"❌ Invalid content_type {model_name}")
        except Exception:
            logger.exception("❌ Failed to acknowledge alert")


    # --------------------------------------------------
    #  ALARM / VOICE HANDLER
    # --------------------------------------------------
    async def _trigger_alarm(self, message: str):
        """
        Sends alarm + optional TTS reference to frontend.
        """
        try:
            voice_file = await database_sync_to_async(
                generate_voice_notification_pyttsx3
            )(message)

            await self.send_json({
                "type": "alarm",
                "message": message,
                "voice": voice_file,
                "alarm_sound": "/static/audio/alarm.mp3",
            })

        except Exception:
            logger.exception("⚠️ Alarm trigger failed")
