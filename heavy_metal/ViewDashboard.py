"""
heavy_metal/ViewDashboard.py — Heavy Metal Telemetry Cockpit
Data-driven monitoring of trace metals, AAS spectrophotometry runs, threshold limits, and quality verification.
"""
import json
import logging
from datetime import timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Avg, Max, Min, Q
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View

from core.mixins import WanjalaMixin
from core.registry import registry
from t.models import HeavyMetalLimit

from .models import (
    HeavyMetalAnalysis,
    HeavyMetalParameter,
    HeavyMetalAnalysisState,
)

logger = logging.getLogger(__name__)


class DashboardView(WanjalaMixin, View):
    template_name = "heavy_metal/dashboard.html"
    app_label = "heavy_metal"

    def get(self, request):
        if (r := self.process_request(request)):
            return r
        self.check_idle_timeout()

        wants_json = (
            "application/json" in request.headers.get("Accept", "")
            or request.GET.get("format") == "json"
        )
        context = self.get_context(request)
        if wants_json:
            return JsonResponse(context.get("dashboard_json_payload", {}), safe=False)

        return HttpResponse(
            render_to_string(self.template_name, context, request=request)
        )

    def get_context(self, request):
        now = timezone.now()
        today = now.date()
        period_days = int(request.GET.get("days", 30))
        start_date = today - timedelta(days=period_days)

        analyses = HeavyMetalAnalysis.objects.filter(analysis_date__gte=start_date)
        total_analyses = analyses.count()
        approved_count = analyses.filter(state=HeavyMetalAnalysisState.APPROVED).count()
        verified_count = analyses.filter(state__in=[HeavyMetalAnalysisState.VERIFIED, HeavyMetalAnalysisState.CONFIRMED]).count()
        pending_count = analyses.filter(state__in=[HeavyMetalAnalysisState.NEW, HeavyMetalAnalysisState.ANALYSED]).count()

        # Parameter values & exceedances
        metal_params = HeavyMetalParameter.objects.filter(analysis__in=analyses).select_related("parameter__parameter")
        total_tests = metal_params.count()

        # Nonconformity / threshold checks
        exceedances = 0
        element_averages = {}
        for p in metal_params[:600]:
            limit = p.parameter
            val = float(p.value or 0)
            elem_name = limit.parameter.name if hasattr(limit, "parameter") and hasattr(limit.parameter, "name") else "Metal"
            element_averages.setdefault(elem_name, []).append(val)

            # Check maximum permissible limit
            max_val = getattr(limit, "max_value", None)
            if max_val is not None and val > float(max_val):
                exceedances += 1

        compliance_rate = (
            round(((total_tests - exceedances) / total_tests) * 100, 1)
            if total_tests > 0
            else 100.0
        )

        kpis = [
            {"label": "Metal Runs", "value": total_analyses, "icon": "fa-atom", "color": "purple"},
            {"label": "Compliance Index", "value": f"{compliance_rate}%", "icon": "fa-shield-halved", "color": "emerald" if compliance_rate >= 98 else "amber"},
            {"label": "Approved Slots", "value": approved_count, "icon": "fa-circle-check", "color": "cyan"},
            {"label": "Pending QA", "value": pending_count, "icon": "fa-clock", "color": "amber"},
            {"label": "Elements Analyzed", "value": len(element_averages), "icon": "fa-vial-virus", "color": "blue"},
            {"label": "Exceedances", "value": exceedances, "icon": "fa-triangle-exclamation", "color": "rose" if exceedances > 0 else "emerald"},
        ]

        # Trend: Daily analysis frequency
        daily_trend = list(
            analyses.values("analysis_date")
            .annotate(count=Count("id"))
            .order_by("analysis_date")
        )

        # Average concentration by metal
        elem_chart_labels = list(element_averages.keys())[:8]
        elem_chart_data = [
            round(sum(element_averages[k]) / len(element_averages[k]), 4)
            for k in elem_chart_labels
        ]

        # State breakdown
        state_counts = list(analyses.values("state").annotate(count=Count("id")).order_by("-count"))
        state_chart = {
            "labels": [d["state"].title() for d in state_counts],
            "data": [d["count"] for d in state_counts],
        }

        # Recent analyses feed
        recent_analyses = []
        for a in analyses.select_related("treatment_plant", "treatment_plant_phase", "analysed_by", "sampling_time").order_by("-analysis_date", "-sampling_time__time")[:10]:
            recent_analyses.append({
                "ref": a.reference_id,
                "plant": str(a.treatment_plant),
                "phase": str(a.treatment_plant_phase),
                "state": a.state,
                "time": a.sampling_time.time.strftime("%H:%M") if a.sampling_time else "—",
                "analyst": a.analysed_by.get_full_name() if a.analysed_by else "—",
                "date": a.analysis_date.strftime("%Y-%m-%d"),
            })

        charts_payload = {
            "daily_trend": {
                "labels": [str(d["analysis_date"]) for d in daily_trend],
                "data": [d["count"] for d in daily_trend],
            },
            "metal_averages": {
                "labels": elem_chart_labels if elem_chart_labels else ["Lead (Pb)", "Cadmium (Cd)", "Arsenic (As)", "Chromium (Cr)", "Mercury (Hg)"],
                "data": elem_chart_data if elem_chart_data else [0.002, 0.001, 0.004, 0.003, 0.0005],
            },
            "states": state_chart,
        }

        try:
            entries = registry.for_app(self.app_label) or []
        except Exception:
            entries = []

        return {
            "dashboard_title": "Heavy Metal Telemetry",
            "dashboard_subtitle": f"Trace Elements & AAS Analytics · {period_days}d",
            "dashboard_icon": "atom",
            "app_groups": registry.sidebar(self.app_label) if entries else [],
            "kpis": kpis,
            "recent_analyses": recent_analyses,
            "charts_json": json.dumps(charts_payload, cls=DjangoJSONEncoder, default=str),
            "dashboard_json_payload": charts_payload,
            "period_days": period_days,
            "total_tests": total_tests,
        }
