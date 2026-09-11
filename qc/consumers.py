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


        self.group_name = None


        if plant:

            self.group_name = (
                f"qc-plant-{plant.pk}"
            )

        elif user.is_superuser:

            self.group_name = (
                "qc-dashboard"
            )


        if self.group_name:

            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name,
            )


        await self.accept()


        await self.send_json(
            {
                "type": "connection.ready",
                "plant_id": getattr(
                    plant,
                    "pk",
                    None,
                ),
                "group": self.group_name,
            }
        )


        logger.info(
            "[QC WS] Connected user=%s plant=%s group=%s",
            user.username,
            getattr(
                plant,
                "pk",
                None,
            ),
            self.group_name,
        )


    async def disconnect(
        self,
        close_code,
    ):


        if self.group_name:

            await self.channel_layer.group_discard(
                self.group_name,
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
            event.get(
                "analysis_id"
            ),
            event.get(
                "plant_id"
            ),
        )


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