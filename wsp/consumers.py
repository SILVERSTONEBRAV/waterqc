import json
from channels.generic.websocket import AsyncWebsocketConsumer
import logging

logger = logging.getLogger(__name__)

class DashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Subscribe to the Celery metrics group
        self.group_name = "celery_metrics"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(f"✅ WebSocket connected: {self.channel_name} subscribed to {self.group_name}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"❌ WebSocket disconnected: {self.channel_name} removed from {self.group_name}")

    async def metrics_update(self, event):
        """
        Receives events sent by `broadcast_task_update` in tasks.py
        """
        try:
            await self.send(text_data=json.dumps(event["data"]))
        except Exception as e:
            logger.warning(f"⚠️ Failed to send WebSocket message: {e}")
