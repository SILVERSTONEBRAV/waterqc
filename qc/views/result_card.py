from __future__ import annotations

import logging

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from core.mixins import WanjalaMixin

from t.models import TreatmentPlant

from qc.models import (
    RawWaterResult,
    TreatedWaterResult,
    CoagulatedWaterResult,
    ClarifiedWaterResult,
    WaterAnalysisLog,
)

from qc.services.result_card_service import ResultCardService


logger = logging.getLogger(__name__)


class ResultCardEntryView(
    WanjalaMixin,
    View,
):

    template_name = "qc/results/result_card.html"

    partial_template_name = (
        "qc/results/_result_cards.html"
    )

    permission_required_view = (
        "qc.change_wateranalysis"
    )


    RESULT_MODELS = {

        "raw":
            RawWaterResult,

        "treated":
            TreatedWaterResult,

        "coagulated":
            CoagulatedWaterResult,

        "clarified":
            ClarifiedWaterResult,

    }


    def dispatch(
        self,
        request,
        *args,
        **kwargs,
    ):

        self.action = (
            "change"
            if request.method == "POST"
            else "view"
        )

        self.check_permission(
            self.action
        )

        return super().dispatch(
            request,
            *args,
            **kwargs
        )


    def get(
        self,
        request,
        *args,
        **kwargs,
    ):

        assignment = (
            self.resolve_user_assignment()
        )

        plant = assignment["plant"]

        laboratory = assignment["laboratory"]


        if not plant:

            return self.render_context({

                "cards": [],

                "plant": None,

                "laboratory":
                    laboratory,

                "entry_mode": True,

                "message":
                    "No treatment plant assigned.",

            })


        context = (
            ResultCardService
            .get_context(
                treatment_plant=plant,
                selected_date=self.resolve_date(),
            )
        )


        context.update({

            "entry_mode": True,

            "auto_refresh": True,

            "current_time":
                timezone.localtime(),

            "plant":
                plant,

            "laboratory":
                laboratory,

        })


        return self.render_context(
            context
        )


    def resolve_user_assignment(
        self,
    ):

        user = self.request.user


        if user.is_superuser:

            plant_id = (
                self.request.GET.get(
                    "plant"
                )
            )


            plant = None


            if plant_id:

                plant = (
                    TreatmentPlant.objects
                    .filter(
                        pk=plant_id
                    )
                    .first()
                )


            if plant is None:

                plant = (
                    TreatmentPlant.objects
                    .order_by(
                        "name"
                    )
                    .first()
                )


            return {

                "plant":
                    plant,

                "laboratory":
                    getattr(
                        user,
                        "assigned_lab",
                        None,
                    ),

            }


        return {

            "plant":
                getattr(
                    user,
                    "assigned_treatment_plant",
                    None,
                ),

            "laboratory":
                getattr(
                    user,
                    "assigned_lab",
                    None,
                ),

        }
    @transaction.atomic
    def post(
        self,
        request,
        *args,
        **kwargs,
    ):

        submitted = (
            self.extract_submitted_values(
                request
            )
        )


        if not submitted:

            messages.warning(
                request,
                "No results entered."
            )

            return self.redirect_back()



        updated = 0

        analysis_ids = set()


        for result_id, raw_value in submitted.items():

            result = (
                self.get_result_locked(
                    result_id
                )
            )


            if result is None:

                continue



            value = (
                self.parse_value(
                    raw_value
                )
            )


            if value is None:

                continue



            result.value = value


            result.save(
                update_fields=[
                    "value",
                    "updated_at",
                ]
            )


            analysis_ids.add(
                result.analysis_id
            )


            updated += 1



        if updated:

            self.create_audit_logs(
                analysis_ids=analysis_ids,
                count=updated,
                user=request.user,
            )


            self.broadcast_results_update(
                analysis_ids
            )


            messages.success(
                request,
                f"{updated} results saved successfully."
            )


        else:

            messages.warning(
                request,
                "No valid values were saved."
            )



        return self.redirect_back()



    def broadcast_results_update(
        self,
        analysis_ids,
    ):

        try:

            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            from qc.models import WaterAnalysis


            channel_layer = (
                get_channel_layer()
            )


            if channel_layer is None:

                return



            analyses = (
                WaterAnalysis.objects
                .filter(
                    id__in=analysis_ids
                )
                .select_related(
                    "treatment_plant",
                    "analysis_time__schedule",
                )
            )



            for analysis in analyses:

                plant = (
                    analysis.treatment_plant
                )


                async_to_sync(
                    channel_layer.group_send
                )(
                    f"qc-plant-{plant.pk}",
                    {
                        "type":
                            "qc_results_updated",

                        "analysis_id":
                            analysis.pk,

                        "plant_id":
                            plant.pk,

                        "water_type":
                            (
                                analysis
                                .analysis_time
                                .schedule
                                .get_water_type_display()
                            ),

                        "timestamp":
                            timezone.now()
                            .isoformat(),
                    },
                )


        except Exception:

            logger.exception(
                "Failed websocket result update."
            )



    def redirect_back(
        self,
    ):

        url = self.request.path


        params = []


        plant = (
            self.request.GET.get(
                "plant"
            )
        )

        date = (
            self.request.GET.get(
                "date"
            )
        )


        if plant:

            params.append(
                f"plant={plant}"
            )


        if date:

            params.append(
                f"date={date}"
            )


        if params:

            url += (
                "?"
                +
                "&".join(params)
            )


        return redirect(
            url
        )



    @staticmethod
    def extract_submitted_values(
        request,
    ):

        values = {}


        for key, value in request.POST.items():

            if not key.startswith(
                "result_"
            ):

                continue


            result_id = (
                key.replace(
                    "result_",
                    "",
                )
            )


            if result_id.isdigit():

                values[
                    int(result_id)
                ] = value.strip()


        return values



    def get_result_locked(
        self,
        result_id,
    ):

        for model in (
            self.RESULT_MODELS.values()
        ):

            try:

                return (
                    model.objects
                    .select_for_update()
                    .get(
                        pk=result_id
                    )
                )


            except ObjectDoesNotExist:

                continue


        return None



    @staticmethod
    def parse_value(
        value,
    ):

        if not value:

            return None


        try:

            return Decimal(
                value
            )


        except InvalidOperation:

            return None



    @staticmethod
    def create_audit_logs(
        analysis_ids,
        count,
        user,
    ):

        for analysis_id in analysis_ids:

            WaterAnalysisLog.objects.create(

                analysis_id=
                    analysis_id,

                action=
                    "results_entered",

                remarks=
                    f"{count} results entered manually.",

                actor=
                    user,

                auto_generated=
                    False,

            )



    def resolve_date(
        self,
    ):

        value = (
            self.request.GET.get(
                "date"
            )
        )


        if not value:

            return timezone.localdate()



        try:

            return datetime.strptime(
                value,
                "%Y-%m-%d",
            ).date()


        except ValueError:

            return timezone.localdate()



    def render_context(
        self,
        context,
    ):

        template = (

            self.partial_template_name

            if (
                self.is_htmx()

                or

                self.request.GET.get(
                    "partial"
                )
                ==
                "cards"
            )

            else self.template_name

        )


        response = render(
            self.request,
            template,
            context,
        )


        response[
            "X-Render-Mode"
        ] = (

            "partial"

            if template ==
            self.partial_template_name

            else

            "full"

        )


        response[
            "X-Generated-At"
        ] = (
            timezone.now()
            .isoformat()
        )


        response[
            "Cache-Control"
        ] = (
            "no-store, "
            "no-cache, "
            "must-revalidate, "
            "max-age=0"
        )


        if context.get(
            "plant"
        ):

            response[
                "X-Plant-ID"
            ] = str(
                context["plant"].pk
            )


        if context.get(
            "laboratory"
        ):

            response[
                "X-Laboratory-ID"
            ] = str(
                context["laboratory"].pk
            )


        return response