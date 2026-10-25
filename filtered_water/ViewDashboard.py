"""
filtered_water/ViewDashboard.py — Advanced Filtered Water Telemetry Cockpit
Data-driven monitoring of water filtration, limits compliance, filter statuses, and verification workflows.
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
from t.models import WaterFilter, FilteredWaterLimit

from .models import (
    FilteredWaterAnalysis,
    FilteredWaterResults,
    FilteredWaterAnalysisState,
    WaterFilterStatus,
)

logger = logging.getLogger(__name__)


class DashboardView(WanjalaMixin, View):
    template_name = "filtered_water/dashboard.html"
    app_label = "filtered_water"

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

        analyses = FilteredWaterAnalysis.objects.filter(created_at__date__gte=start_date)
        total_analyses = analyses.count()
        verified_count = analyses.filter(state=FilteredWaterAnalysisState.VERIFIED.value).count()
        pending_verification = analyses.filter(state=FilteredWaterAnalysisState.ANALYSED.value).count()
        new_count = analyses.filter(state=FilteredWaterAnalysisState.NEW.value).count()

        filters = WaterFilter.objects.all()
        total_filters = filters.count()
        working_filters = filters.filter(status=WaterFilterStatus.WORKING.value).count()
        backwashing_filters = filters.filter(status=WaterFilterStatus.BACKWASHING.value).count()
        isolated_filters = filters.filter(status=WaterFilterStatus.ISOLATED.value).count()

        # Results & Compliance
        results = FilteredWaterResults.objects.filter(analysis__in=analyses).select_related("parameter", "water_filter")
        total_results = results.count()

        # Calculate limits compliance
        compliant_count = 0
        non_compliant_count = 0
        for res in results[:500]:
            limit = res.parameter
            val = float(res.result_value or 0)
            is_ok = True
            if hasattr(limit, "min_value") and limit.min_value is not None and val < float(limit.min_value):
                is_ok = False
            if hasattr(limit, "max_value") and limit.max_value is not None and val > float(limit.max_value):
                is_ok = False
            if is_ok:
                compliant_count += 1
            else:
                non_compliant_count += 1

        compliance_rate = (
            round((compliant_count / (compliant_count + non_compliant_count)) * 100, 1)
            if (compliant_count + non_compliant_count) > 0
            else 100.0
        )

        kpis = [
            {"label": "Analyses Logged", "value": total_analyses, "icon": "fa-filter", "color": "cyan"},
            {"label": "Compliance Rate", "value": f"{compliance_rate}%", "icon": "fa-shield-halved", "color": "emerald" if compliance_rate >= 95 else "amber"},
            {"label": "Verified Runs", "value": verified_count, "icon": "fa-circle-check", "color": "blue"},
            {"label": "Pending Review", "value": pending_verification, "icon": "fa-clock", "color": "purple"},
            {"label": "Working Filters", "value": f"{working_filters}/{total_filters}", "icon": "fa-faucet-drip", "color": "emerald"},
            {"label": "In Backwash/Iso", "value": backwashing_filters + isolated_filters, "icon": "fa-wrench", "color": "amber" if backwashing_filters > 0 else "rose"},
        ]

        # Trend: Daily analyses
        daily_trend = list(
            analyses.values("created_at__date")
            .annotate(count=Count("id"))
            .order_by("created_at__date")
        )

        # Filter status breakdown
        status_data = {
            "labels": ["Working", "Backwashing", "Isolated"],
            "data": [working_filters, backwashing_filters, isolated_filters],
        }

        # State breakdown
        state_data = {
            "labels": ["Verified", "Analysed", "New"],
            "data": [verified_count, pending_verification, new_count],
        }

        # Recent analyses feed
        recent_analyses = []
        for a in analyses.select_related("treatment_plant", "treatment_plant_phase", "analysed_by").order_by("-created_at")[:10]:
            recent_analyses.append({
                "uuid": str(a.uuid)[:8],
                "plant": str(a.treatment_plant),
                "phase": str(a.treatment_plant_phase),
                "state": a.state,
                "analyst": a.analysed_by.get_full_name() if a.analysed_by else "—",
                "date": a.created_at.strftime("%Y-%m-%d %H:%M"),
            })

        charts_payload = {
            "daily_trend": {
                "labels": [str(d["created_at__date"]) for d in daily_trend],
                "data": [d["count"] for d in daily_trend],
            },
            "filter_status": status_data,
            "state_breakdown": state_data,
        }

        try:
            entries = registry.for_app(self.app_label) or []
        except Exception:
            entries = []

        return {
            "dashboard_title": "Filtered Water Quality",
            "dashboard_subtitle": f"Filtration Telemetry & Compliance · {period_days}d",
            "dashboard_icon": "filter",
            "app_groups": registry.sidebar(self.app_label) if entries else [],
            "kpis": kpis,
            "recent_analyses": recent_analyses,
            "charts_json": json.dumps(charts_payload, cls=DjangoJSONEncoder, default=str),
            "dashboard_json_payload": charts_payload,
            "period_days": period_days,
            "working_filters": working_filters,
            "total_filters": total_filters,
        }
