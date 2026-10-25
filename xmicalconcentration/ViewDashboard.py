"""
xmicalconcentration/ViewDashboard.py — Chemical Concentration Cockpit
Tracks hydrometer readings, concentration calculations, and trend analytics.
"""
import json
import logging
from collections import defaultdict
from datetime import timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Avg, Count, Max, Min, Sum
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View

from core.mixins import WanjalaMixin
from core.registry import registry

from .models import XmicalConcentration

logger = logging.getLogger(__name__)


class DashboardView(WanjalaMixin, View):
    template_name = "xmicalconcentration/dashboard.html"
    app_label = "xmicalconcentration"

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
        return HttpResponse(render_to_string(self.template_name, context, request=request))

    def get_context(self, request):
        now = timezone.now()
        today = now.date()
        period_days = int(request.GET.get("days", 30))
        start_date = today - timedelta(days=period_days)

        qs = XmicalConcentration.objects.filter(measurement_date__date__gte=start_date)
        qs_today = qs.filter(measurement_date__date=today)

        agg = qs.aggregate(
            avg_conc=Avg("concentration_mg_per_l"),
            min_conc=Min("concentration_mg_per_l"),
            max_conc=Max("concentration_mg_per_l"),
            avg_reading=Avg("hydrometer_reading"),
        )

        kpis = [
            {"label": "Measurements", "value": qs.count(), "icon": "fa-vial-circle-check", "color": "cyan"},
            {"label": "Today", "value": qs_today.count(), "icon": "fa-calendar-day", "color": "emerald"},
            {"label": "Avg Conc (mg/L)", "value": f"{float(agg['avg_conc'] or 0):.1f}", "icon": "fa-gauge-high", "color": "blue"},
            {"label": "Min Conc", "value": f"{float(agg['min_conc'] or 0):.1f}", "icon": "fa-arrow-down", "color": "amber"},
            {"label": "Max Conc", "value": f"{float(agg['max_conc'] or 0):.1f}", "icon": "fa-arrow-up", "color": "rose"},
            {"label": "Avg Reading", "value": f"{float(agg['avg_reading'] or 0):.3f}", "icon": "fa-ruler-vertical", "color": "purple"},
            {"label": "Chemicals", "value": qs.values("chemical_name").distinct().count(), "icon": "fa-flask", "color": "cyan"},
            {"label": "Tanks", "value": qs.values("tank").distinct().count(), "icon": "fa-oil-can", "color": "slate"},
        ]

        # Concentration trend
        conc_trend = list(
            qs.values("measurement_date__date")
            .annotate(avg=Avg("concentration_mg_per_l"), count=Count("id"))
            .order_by("measurement_date__date")
        )

        # By chemical
        by_chemical = list(
            qs.values("chemical_name")
            .annotate(avg=Avg("concentration_mg_per_l"), count=Count("id"))
            .order_by("-count")[:10]
        )

        # By tank
        by_tank = list(
            qs.values("tank__name")
            .annotate(avg=Avg("concentration_mg_per_l"), count=Count("id"))
            .order_by("-count")[:10]
        )

        # Recent measurements
        recent = []
        for m in qs.select_related("tank", "measured_by")[:15]:
            recent.append({
                "chemical": m.chemical_name,
                "concentration": float(m.concentration_mg_per_l),
                "reading": float(m.hydrometer_reading),
                "tank": str(m.tank) if m.tank else "—",
                "by": str(m.measured_by) if m.measured_by else "—",
                "date": m.measurement_date.strftime("%Y-%m-%d %H:%M"),
            })

        charts_payload = {
            "conc_trend": {
                "labels": [str(d["measurement_date__date"]) for d in conc_trend],
                "data": [float(d["avg"] or 0) for d in conc_trend],
                "counts": [d["count"] for d in conc_trend],
            },
            "by_chemical": {
                "labels": [d["chemical_name"] for d in by_chemical],
                "data": [float(d["avg"] or 0) for d in by_chemical],
            },
            "by_tank": {
                "labels": [d["tank__name"] or "—" for d in by_tank],
                "data": [float(d["avg"] or 0) for d in by_tank],
            },
        }

        try:
            entries = registry.for_app(self.app_label) or []
        except Exception:
            entries = []

        return {
            "dashboard_title": "Chemical Concentration",
            "dashboard_subtitle": f"Hydrometer Analytics · {period_days}d",
            "dashboard_icon": "vial-circle-check",
            "app_groups": registry.sidebar(self.app_label) if entries else [],
            "kpis": kpis,
            "recent": recent,
            "charts_json": json.dumps(charts_payload, cls=DjangoJSONEncoder, default=str),
            "dashboard_json_payload": charts_payload,
            "period_days": period_days,
        }
