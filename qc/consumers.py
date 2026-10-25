from __future__ import annotations

import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer


logger = logging.getLogger(__name__)


class DashboardConsumer(
    AsyncJsonWebsocketConsumer
):

    async def connect(self):

        user = self.scope.get(
            "user"
        )

        if not user or user.is_anonymous:

            await self.close(
                code=4001
            )

            return

        if not user.is_superuser and not (
            user.has_perm("qc.view_wateranalysis")
            or user.has_perm("qc.change_wateranalysis")
        ):
            await self.close(code=4003)
            return


        plant = getattr(
            user,
            "assigned_treatment_plant",
            None,
        )


        if not plant and not user.is_superuser:

            await self.close(
                code=4002
            )

            return


        query_string = self.scope.get("query_string", b"").decode("utf-8")
        from urllib.parse import parse_qs
        qs = parse_qs(query_string)
        url_plant = qs.get("plant", [None])[0]

        self.groups_joined = []
        if plant:
            self.groups_joined.append(f"qc-plant-{plant.pk}")
        if user.is_superuser and url_plant:
            from asgiref.sync import sync_to_async
            from t.models import TreatmentPlant

            exists = await sync_to_async(
                TreatmentPlant.objects.filter(pk=url_plant).exists
            )()
            if exists:
                self.groups_joined.append(f"qc-plant-{url_plant}")
        if user.is_superuser and "qc-dashboard" not in self.groups_joined:
            self.groups_joined.append("qc-dashboard")

        for g in self.groups_joined:
            await self.channel_layer.group_add(
                g,
                self.channel_name,
            )

        await self.accept()

        await self.send_json(
            {
                "type": "connection.ready",
                "plant_id": getattr(
                    plant,
                    "pk",
                    url_plant,
                ),
                "groups": self.groups_joined,
            }
        )

        logger.info(
            "[QC WS] Connected user=%s plant=%s groups=%s",
            user.username,
            getattr(
                plant,
                "pk",
                url_plant,
            ),
            self.groups_joined,
        )

    async def disconnect(
        self,
        close_code,
    ):
        for g in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(
                g,
                self.channel_name,
            )

        logger.info(
            "[QC WS] Disconnected code=%s user=%s",
            close_code,
            self.scope.get(
                "user"
            ),
        )


    async def qc_results_updated(
        self,
        event,
    ):


        await self.send_json(
            {
                "type": "results.updated",
                "analysis_id": event.get(
                    "analysis_id"
                ),
                "plant_id": event.get(
                    "plant_id"
                ),
                "water_type": event.get(
                    "water_type"
                ),
                "timestamp": event.get(
                    "timestamp"
                ),
            }
        )

        logger.info(
            "[QC WS] Results update sent analysis=%s plant=%s",
            event.get("analysis_id"),
            event.get("plant_id"),
        )


    async def qc_results_changed(self, event):
        """Send a durable outbox invalidation; clients re-fetch scoped HTML."""
        await self.send_json({
            "type": "results.changed",
            "event_id": event.get("event_id"),
            "analysis_id": event.get("analysis_id"),
            "plant_id": event.get("plant_id"),
            "water_type": event.get("water_type"),
            "action": event.get("action"),
            "changed_model": event.get("changed_model"),
            "timestamp": event.get("timestamp"),
        })


    async def qc_nonconformity_created(self, event):
        """Deliver a newly auto-detected result exception to the QC bell UI."""
        await self.send_json({
            "type": "qc_nonconformity",
            "nonconformity_id": event.get("nonconformity_id"),
            "analysis_id": event.get("analysis_id"),
            "plant_id": event.get("plant_id"),
            "parameter_name": event.get("parameter_name"),
            "observed_value": event.get("observed_value"),
            "min_limit": event.get("min_limit"),
            "max_limit": event.get("max_limit"),
            "timestamp": event.get("timestamp"),
        })


    async def analysis_created(
        self,
        event,
    ):


        await self.send_json(
            {
                "type": "analysis.created",
                "analysis_id": event.get(
                    "analysis_id"
                ),
                "plant_id": event.get(
                    "plant_id"
                ),
                "water_type": event.get(
                    "water_type"
                ),
                "timestamp": event.get(
                    "timestamp"
                ),
            }
        )


        logger.info(
            "[QC WS] Analysis created sent analysis=%s plant=%s",
            event.get(
                "analysis_id"
            ),
            event.get(
                "plant_id"
            ),
        )


    async def dashboard_refresh(
        self,
        event,
    ):


        await self.send_json(
            {
                "type": "dashboard.refresh",
                "plant_id": event.get(
                    "plant_id"
                ),
                "timestamp": event.get(
                    "timestamp"
                ),
            }
        )


        logger.info(
            "[QC WS] Dashboard refresh sent plant=%s",
            event.get(
                "plant_id"
            ),
        )
