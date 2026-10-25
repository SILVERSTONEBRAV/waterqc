"""Plant-scoped, data-free invalidation events for connected dashboards."""

from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.apps import apps
from django.utils import timezone


class LiveUpdateConsumer(AsyncJsonWebsocketConsumer):
    """Deliver refresh hints only; clients must reload through normal views."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        query = parse_qs(self.scope.get("query_string", b"").decode("utf-8"))
        app_label = (query.get("app", [""])[0] or "")[:50]
        if app_label:
            try:
                apps.get_app_config(app_label)
            except LookupError:
                app_label = ""

        plant_id = await database_sync_to_async(self._resolve_plant_id)(
            user,
            query.get("plant", [None])[0],
            self.scope.get("session"),
        )
        self.plant_id = plant_id
        self.groups_joined = []
        if plant_id:
            self.groups_joined.append(f"live-plant-{plant_id}")
        if app_label:
            self.groups_joined.append(f"live-app-{app_label}")

        for group in self.groups_joined:
            await self.channel_layer.group_add(group, self.channel_name)

        await self.accept()
        await self.send_json({"type": "connection.ready", "plant_id": plant_id})

    @staticmethod
    def _resolve_plant_id(user, requested_plant, session):
        assigned_id = getattr(user, "assigned_treatment_plant_id", None)
        if not user.is_superuser:
            return assigned_id

        session = session or {}
        plant_id = requested_plant or next(
            (
                session.get(key)
                for key in (
                    "ca_selected_plant",
                    "qc_selected_plant",
                    "selected_plant_id",
                    "selected_treatment_plant_id",
                    "active_plant_id",
                    "plant_id",
                    "treatment_plant_id",
                )
                if session.get(key)
            ),
            None,
        )
        if not plant_id or not str(plant_id).isdigit():
            return None
        return apps.get_model("t", "TreatmentPlant").objects.filter(pk=plant_id).values_list("pk", flat=True).first()

    async def disconnect(self, close_code):
        for group in getattr(self, "groups_joined", ()):
            await self.channel_layer.group_discard(group, self.channel_name)

    async def data_changed(self, event):
        event_plant_id = event.get("plant_id")
        if (
            event_plant_id
            and self.plant_id
            and str(event_plant_id) != str(self.plant_id)
        ):
            return
        await self.send_json({
            "type": "data.changed",
            "app_label": event.get("app_label"),
            "model": event.get("model"),
            "action": event.get("action"),
            "plant_id": event.get("plant_id"),
            "timestamp": event.get("timestamp") or timezone.now().isoformat(),
        })
