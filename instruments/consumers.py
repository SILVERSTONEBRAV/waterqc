# instruments/consumers.py
import json
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import Instrument, Sensor
from .tasks import process_sensor_measurements


class InstrumentConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time instrument updates.
    Listens for incoming MQTT-like payloads or dashboard requests.
    Broadcasts threshold alerts and latest measurements to subscribed clients.
    """

    async def connect(self):
        """
        Accept connection and optionally join instrument-specific groups.
        """
        await self.accept()
        await self.send_json({"status": "connected"})

    async def disconnect(self, code):
        """
        Clean up on disconnect.
        """
        # Leave all groups
        groups = getattr(self, "groups_joined", [])
        for group in groups:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """
        Handle incoming messages. Expected payload:

        {
            "instrument_uuid": "uuid",
            "readings": [
                {"sensor_uuid": "uuid", "value": 2.5, "measured_at": "..."},
                ...
            ]
        }
        """
        try:
            instrument_uuid = content.get("instrument_uuid")
            readings = content.get("readings", [])

            if not instrument_uuid or not readings:
                await self.send_json({"status": "error", "detail": "Missing instrument_uuid or readings"})
                return

            # Pre-flag stale/invalid readings
            for reading in readings:
                try:
                    sensor = await sync_to_async(Sensor.objects.select_related("instrument").get)(uuid=reading["sensor_uuid"])
                    if sensor.instrument.is_stale():
                        reading["quality_flag"] = "stale"
                except Sensor.DoesNotExist:
                    reading["quality_flag"] = "invalid"

            # Enqueue Celery task for async ingestion
            await sync_to_async(process_sensor_measurements.delay)(content)

            # Add this client to instrument group for real-time updates
            group_name = f"instrument_{instrument_uuid}"
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.groups_joined = getattr(self, "groups_joined", [])
            if group_name not in self.groups_joined:
                self.groups_joined.append(group_name)

            await self.send_json({"status": "queued", "instrument_uuid": instrument_uuid})

        except Exception as e:
            await self.send_json({"status": "error", "detail": str(e)})

    # -------------------------
    # Group event handlers
    # -------------------------
    async def threshold_alert(self, event):
        """
        Broadcast threshold alerts to WebSocket clients.
        Event structure: {"type": "threshold_alert", "message": {...}}
        """
        await self.send_json({
            "event": "threshold_alert",
            "payload": event["message"]
        })

    async def latest_measurement_update(self, event):
        """
        Broadcast latest measurement update.
        Event structure: {"type": "latest_measurement_update", "message": {...}}
        """
        await self.send_json({
            "event": "latest_measurement",
            "payload": event["message"]
        })

    async def instrument_status_update(self, event):
        """
        Broadcast instrument status updates.
        Event structure: {"type": "instrument_status_update", "message": {...}}
        """
        await self.send_json({
            "event": "instrument_status",
            "payload": event["message"]
        })


# -------------------------
# Optional helper function
# -------------------------
async def broadcast_instrument_status(instrument_uuid, status, last_seen=None):
    """
    Utility to send instrument status updates to group.
    Can be called from Celery tasks or signal handlers.
    """
    from channels.layers import get_channel_layer
    channel_layer = get_channel_layer()
    payload = {"uuid": instrument_uuid, "status": status, "last_seen": last_seen or timezone.now().isoformat()}
    await channel_layer.group_send(
        f"instrument_{instrument_uuid}",
        {
            "type": "instrument_status_update",
            "message": payload
        }
    )
