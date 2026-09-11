import json
from channels.generic.websocket import AsyncWebsocketConsumer
from qc_analytics.engine import QCAnalyticsEngine
from datetime import datetime


class QCAnalyticsConsumer(AsyncWebsocketConsumer):
    """
    Advanced real-time QC analytics consumer.

    Features:
    - Dynamic subscription to parameters/phases
    - Streams anomaly, stats, forecast, AI summary updates
    - Sends task progress updates
    - Provides optional historical snapshot on connect
    """

    async def connect(self):
        # Default group for all analytics
        self.groups_to_subscribe = ["qc_analytics"]
        await self.channel_layer.group_add("qc_analytics", self.channel_name)
        await self.accept()

        # Send connection acknowledgment
        await self.send(json.dumps({
            "status": "connected",
            "message": "QC analytics stream active.",
            "timestamp": datetime.now().isoformat()
        }))

        # Optionally send last cached snapshot
        try:
            import django.core.cache as cache
            last_snapshot = cache.cache.get("qc_last_snapshot")
            if last_snapshot:
                await self.send(json.dumps({
                    "type": "historical_snapshot",
                    "payload": last_snapshot
                }))
        except Exception:
            pass

    async def disconnect(self, close_code):
        for group in self.groups_to_subscribe:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive(self, text_data):
        """
        Handle incoming messages to:
        - Subscribe/unsubscribe dynamically
        - Request one-off analytics
        """
        try:
            data = json.loads(text_data)
            action = data.get("action")

            if action == "subscribe":
                group = data.get("group")
                if group and group not in self.groups_to_subscribe:
                    await self.channel_layer.group_add(group, self.channel_name)
                    self.groups_to_subscribe.append(group)
                    await self.send(json.dumps({"status": "subscribed", "group": group}))

            elif action == "unsubscribe":
                group = data.get("group")
                if group and group in self.groups_to_subscribe:
                    await self.channel_layer.group_discard(group, self.channel_name)
                    self.groups_to_subscribe.remove(group)
                    await self.send(json.dumps({"status": "unsubscribed", "group": group}))

            elif action == "fetch":
                # One-off analytics request
                param = data.get("parameter")
                phase = data.get("phase")
                start = data.get("start")
                end = data.get("end")
                forecast_method = data.get("forecast_method", "hybrid")
                periods = int(data.get("periods", 30))

                df = QCAnalyticsEngine.get_data(param, phase, start, end)
                df = QCAnalyticsEngine.detect_anomalies(df)
                stats = QCAnalyticsEngine.generate_statistics(df)
                forecast = QCAnalyticsEngine.forecast(df, param, forecast_method, periods)
                anomalies = df[df["anomaly"]].to_dict(orient="records")

                payload = {
                    "parameter": param,
                    "phase": phase,
                    "stats": stats,
                    "forecast": forecast,
                    "anomalies": anomalies
                }
                await self.send(json.dumps({"type": "one_off_update", "payload": payload}))

        except Exception as e:
            await self.send(json.dumps({"type": "error", "message": str(e)}))

    async def analytics_update(self, event):
        """
        Handle pushed analytics updates from Celery/WebSocket group.
        Event payload contains:
        - parameter, phase, stats, anomalies, forecast, correlations, AI summary
        """
        try:
            await self.send(json.dumps({
                "type": "analytics_update",
                "payload": event["data"]
            }))
        except Exception as e:
            await self.send(json.dumps({"type": "error", "message": str(e)}))

    async def analytics_progress(self, event):
        """
        Receive task progress updates from Celery.
        Event payload contains:
        - percent, message
        """
        try:
            await self.send(json.dumps({
                "type": "analytics_progress",
                "payload": event["data"]
            }))
        except Exception as e:
            await self.send(json.dumps({"type": "error", "message": str(e)}))
