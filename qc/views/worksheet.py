from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from core.mixins import WanjalaMixin
from qc.models import WaterAnalysis


# ==========================================================
# RESULT MODEL RESOLVER
# ==========================================================

def get_result_model(water_type):
    from qc.models import (
        RawWaterResult,
        TreatedWaterResult,
        ClarifiedWaterResult,
        CoagulatedWaterResult,
    )

    mapping = {
        "raw": RawWaterResult,
        "treated": TreatedWaterResult,
        "clarified": ClarifiedWaterResult,
        "coagulated": CoagulatedWaterResult,
    }

    return mapping.get(str(water_type).lower())


# ==========================================================
# WORKSHEET VIEW
# ==========================================================

class AnalysisWorksheetView(
    WanjalaMixin,
    TemplateView,
):
    template_name = "qc/analysis/worksheet.html"
    permission_required_view = "qc.view_wateranalysis"

    breadcrumbs = [
        {
            "title": "Water Analysis Worksheet",
            "url": None,
        }
    ]

    def get_selected_date(self):
        value = self.request.GET.get("date")

        if not value:
            return timezone.localdate()

        try:
            return timezone.datetime.strptime(
                value,
                "%Y-%m-%d"
            ).date()
        except Exception:
            return timezone.localdate()

    def get_queryset(self):
        qs = (
            WaterAnalysis.objects
            .select_related(
                "treatment_plant",
                "analysis_time",
                "shift",
            )
            .order_by(
                "analysis_time__time",
                "analysis_time__schedule__water_type",
                "treatment_plant__name",
            )
        )

        qs = self.filter_by_user_plant(qs)

        date = self.get_selected_date()

        qs = qs.filter(
            analysis_date=date,
        )

        if date == timezone.localdate() and not qs.exists():
            from qc.services.analysis_generator import AnalysisGenerator
            AnalysisGenerator.generate_due_analyses()
            qs = self.filter_by_user_plant(
                WaterAnalysis.objects
                .select_related(
                    "treatment_plant",
                    "analysis_time",
                    "shift",
                )
                .order_by(
                    "analysis_time__time",
                    "analysis_time__schedule__water_type",
                    "treatment_plant__name",
                )
            ).filter(analysis_date=date)

        plant = self.request.GET.get("plant")

        if plant:
            qs = qs.filter(
                treatment_plant_id=plant
            )

        shift = self.request.GET.get("shift")

        if shift:
            qs = qs.filter(
                shift_id=shift
            )

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        analyses = self.get_queryset()

        worksheets = []

        summary = defaultdict(int)

        for analysis in analyses:

            ResultModel = get_result_model(
                analysis.water_type
            )

            if not ResultModel:
                continue

            results = (
                ResultModel.objects
                .filter(
                    analysis=analysis
                )
                .select_related(
                    "parameter"
                )
                .order_by(
                    "parameter__parameter__name",
                )
            )

            total = results.count()

            completed = results.exclude(
                value__isnull=True,
            ).count()

            abnormal = 0  # computed in template via limit comparison

            worksheets.append(
                {
                    "analysis": analysis,
                    "results": results,
                    "total": total,
                    "completed": completed,
                    "abnormal": abnormal,
                    "progress": (
                        completed * 100 // total
                        if total
                        else 0
                    ),
                }
            )

            summary["tables"] += 1
            summary["results"] += total
            summary["completed"] += completed
            summary["abnormal"] += abnormal

        ctx["selected_date"] = (
            self.get_selected_date()
        )

        ctx["worksheets"] = worksheets
        ctx["summary"] = summary

        return ctx


# ==========================================================
# SAVE ALL RESULTS
# ==========================================================

class AnalysisWorksheetSaveView(
    WanjalaMixin,
    View,
):
    permission_required_update = (
        "qc.change_wateranalysis"
    )

    def post(self, request, *args, **kwargs):

        self.check_permission("update")

        updated = 0
        completed_analyses = set()

        with transaction.atomic():

            for key, value in request.POST.items():

                if not key.startswith(
                    "result_"
                ):
                    continue

                if value in [
                    "",
                    None,
                ]:
                    continue

                try:
                    result_id = int(
                        key.replace(
                            "result_",
                            "",
                        )
                    )
                except Exception:
                    continue

                result = self.get_result_object(
                    result_id
                )

                if not result:
                    continue

                try:
                    result.value = Decimal(
                        str(value)
                    )
                except (
                    InvalidOperation,
                    TypeError,
                    ValueError,
                ):
                    continue

                fields = ["value"]

                if hasattr(
                    result,
                    "entered_at",
                ):
                    result.entered_at = (
                        timezone.now()
                    )
                    fields.append(
                        "entered_at"
                    )

                if hasattr(
                    result,
                    "entered_by",
                ):
                    result.entered_by = (
                        request.user
                    )
                    fields.append(
                        "entered_by"
                    )

                result.full_clean()
                result.save(
                    update_fields=fields
                )

                completed_analyses.add(
                    result.analysis_id
                )

                updated += 1

            analyses = (
                WaterAnalysis.objects
                .filter(
                    pk__in=completed_analyses
                )
            )

            for analysis in analyses:

                if hasattr(
                    analysis,
                    "analysed_by",
                ):
                    analysis.analysed_by = (
                        request.user
                    )

                if hasattr(
                    analysis,
                    "analysis_completed_at",
                ):
                    analysis.analysis_completed_at = (
                        timezone.now()
                    )

                analysis.save()

        messages.success(
            request,
            f"{updated} result(s) saved successfully."
        )

        if request.headers.get(
            "HX-Request"
        ):
            return JsonResponse(
                {
                    "success": True,
                    "updated": updated,
                }
            )

        return redirect(
            reverse(
                "qc:analysis-worksheet"
            )
        )

    def get_result_object(
        self,
        result_id,
    ):
        models = [
            "RawWaterResult",
            "TreatedWaterResult",
            "ClarifiedWaterResult",
            "CoagulatedWaterResult",
        ]

        for model_name in models:

            try:
                from django.apps import apps

                Model = apps.get_model(
                    "qc",
                    model_name,
                )

                obj = (
                    Model.objects
                    .select_related(
                        "analysis"
                    )
                    .filter(
                        pk=result_id
                    )
                    .first()
                )

                if obj:
                    return obj

            except Exception:
                continue

        return None