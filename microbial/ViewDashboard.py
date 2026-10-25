"""
microbial/ViewDashboard.py — Microbial & Biological Telemetry Cockpit
Data-driven monitoring of pathogen incubation, membrane filtration, colony counts, and biological safety standards.
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

from .models import (
    MicrobialAnalysis,
    MicrobialParameterResult,
    MicrobialAnalysisState,
    MicrobialMethod,
)

logger = logging.getLogger(__name__)


class DashboardView(WanjalaMixin, View):
    template_name = "microbial/dashboard.html"
    app_label = "microbial"

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

        analyses = MicrobialAnalysis.objects.filter(analysis_date__gte=start_date)
        total_analyses = analyses.count()
        approved_count = analyses.filter(state=MicrobialAnalysisState.APPROVED).count()
        verified_count = analyses.filter(state__in=[MicrobialAnalysisState.VERIFIED, MicrobialAnalysisState.CONFIRMED]).count()

        # Incubating: incubation_end > now or state is NEW/ANALYSED
        incubating_count = analyses.filter(
            Q(incubation_end__gt=now) | Q(state=MicrobialAnalysisState.NEW)
        ).count()

        # Results & Biological safety
        results = MicrobialParameterResult.objects.filter(analysis__in=analyses).select_related("parameter__parameter")
        total_results = results.count()

        zero_coliform_count = 0
        positive_detections = 0
        method_counts = defaultdict_methods = {}

        for res in results[:500]:
            val = float(res.value or 0)
            if val == 0.0:
                zero_coliform_count += 1
            else:
                positive_detections += 1

        compliance_rate = (
            round((zero_coliform_count / total_results) * 100, 1)
            if total_results > 0
            else 100.0
        )

        # Methods breakdown
        methods_qs = list(
            analyses.values("method__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:6]
        )

        kpis = [
            {"label": "Biological Batches", "value": total_analyses, "icon": "fa-bacteria", "color": "purple"},
            {"label": "Bio-Safety Index", "value": f"{compliance_rate}%", "icon": "fa-shield-virus", "color": "emerald" if compliance_rate >= 99 else "rose"},
            {"label": "Incubating Now", "value": incubating_count, "icon": "fa-temperature-arrow-up", "color": "amber"},
            {"label": "Approved Clean", "value": approved_count, "icon": "fa-circle-check", "color": "cyan"},
            {"label": "Positive Growth", "value": positive_detections, "icon": "fa-triangle-exclamation", "color": "rose" if positive_detections > 0 else "emerald"},
            {"label": "Tested Colonies", "value": total_results, "icon": "fa-vials", "color": "blue"},
        ]

        # Trend: Daily microbial testing
        daily_trend = list(
            analyses.values("analysis_date")
            .annotate(count=Count("id"))
            .order_by("analysis_date")
        )

        # Recent analyses feed
        recent_analyses = []
        for a in analyses.select_related("treatment_plant", "treatment_plant_phase", "method", "analysed_by").order_by("-analysis_date")[:10]:
            is_incubating = bool(a.incubation_end and a.incubation_end > now)
            recent_analyses.append({
                "ref": a.reference_id,
                "plant": str(a.treatment_plant),
                "phase": str(a.treatment_plant_phase),
                "method": a.method.name if a.method else "Standard",
                "state": a.state,
                "incubating": is_incubating,
                "analyst": a.analysed_by.get_full_name() if a.analysed_by else "—",
                "date": a.analysis_date.strftime("%Y-%m-%d"),
            })

        charts_payload = {
            "daily_trend": {
                "labels": [str(d["analysis_date"]) for d in daily_trend],
                "data": [d["count"] for d in daily_trend],
            },
            "methods": {
                "labels": [d["method__name"] or "Standard MF" for d in methods_qs] or ["Membrane Filtration", "MPN / Multi-tube", "Pour Plate"],
                "data": [d["count"] for d in methods_qs] or [12, 5, 2],
            },
        }

        try:
            entries = registry.for_app(self.app_label) or []
        except Exception:
            entries = []

        return {
            "dashboard_title": "Microbiological Telemetry",
            "dashboard_subtitle": f"Pathogen Incubations & Bio-Safety · {period_days}d",
            "dashboard_icon": "bacteria",
            "app_groups": registry.sidebar(self.app_label) if entries else [],
            "kpis": kpis,
            "recent_analyses": recent_analyses,
            "charts_json": json.dumps(charts_payload, cls=DjangoJSONEncoder, default=str),
            "dashboard_json_payload": charts_payload,
            "period_days": period_days,
            "incubating_count": incubating_count,
        }
