"""
backwashing/ViewDashboard.py — Advanced Telemetry Cockpit
Data-driven dashboard for Backwashing, Desludging & Pump Flush operations.
"""
import json
import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Avg, Count, Max, Min, Sum, Q, F
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View

from core.mixins import WanjalaMixin
from core.registry import registry

from .models import Backwashing, Disludging, PumpFlush, PhaseLossRate

logger = logging.getLogger(__name__)


class DashboardView(WanjalaMixin, View):
    """
    Advanced cockpit dashboard for Backwashing operations.
    Provides real-time KPIs, trend charts, water-loss analytics,
    filter utilization heatmaps, and operator performance metrics.
    """

    template_name = "backwashing/dashboard.html"
    app_label = "backwashing"

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
            return JsonResponse(context["dashboard_json_payload"], safe=False)

        return HttpResponse(
            render_to_string(self.template_name, context, request=request)
        )

    # ─── Context Pipeline ───
    def get_context(self, request):
        now = timezone.now()
        today = now.date()
        period_days = int(request.GET.get("days", 30))
        start_date = today - timedelta(days=period_days)

        # Querysets
        bw_qs = Backwashing.objects.filter(start_time__date__gte=start_date)
        ds_qs = Disludging.objects.filter(start_time__date__gte=start_date)
        pf_qs = PumpFlush.objects.filter(start_time__date__gte=start_date)

        bw_today = bw_qs.filter(start_time__date=today)
        ds_today = ds_qs.filter(start_time__date=today)
        pf_today = pf_qs.filter(start_time__date=today)

        # KPI metrics
        kpis = self._build_kpis(bw_qs, ds_qs, pf_qs, bw_today, ds_today, pf_today)

        # Trend data (daily aggregation)
        bw_trend = self._build_daily_trend(bw_qs, start_date, today)
        ds_trend = self._build_daily_trend(ds_qs, start_date, today)
        water_loss_trend = self._build_water_loss_trend(bw_qs, ds_qs, pf_qs, start_date, today)

        # Status distribution
        status_dist = self._build_status_distribution(bw_qs)

        # Filter utilization
        filter_util = self._build_filter_utilization(bw_qs)

        # Recent operations
        recent_ops = self._build_recent_ops(bw_qs, ds_qs, pf_qs)

        # Operator leaderboard
        operator_stats = self._build_operator_stats(bw_qs, ds_qs, pf_qs)

        # Duration analytics
        duration_stats = self._build_duration_stats(bw_qs, ds_qs, pf_qs)

        # Registry entries
        try:
            entries = registry.for_app(self.app_label) or []
        except Exception:
            entries = []

        charts_payload = {
            "bw_trend": bw_trend,
            "ds_trend": ds_trend,
            "water_loss_trend": water_loss_trend,
            "status_distribution": status_dist,
            "filter_utilization": filter_util,
            "duration_stats": duration_stats,
        }

        return {
            "dashboard_title": "Backwashing Operations",
            "dashboard_subtitle": f"Last {period_days} days telemetry",
            "dashboard_icon": "arrows-rotate",
            "app_groups": registry.sidebar(self.app_label) if entries else [],
            "kpis": kpis,
            "recent_ops": recent_ops,
            "operator_stats": operator_stats,
            "charts_json": json.dumps(charts_payload, cls=DjangoJSONEncoder, default=str),
            "dashboard_json_payload": charts_payload,
            "period_days": period_days,
        }

    # ─── KPI Builder ───
    def _build_kpis(self, bw_qs, ds_qs, pf_qs, bw_today, ds_today, pf_today):
        total_ops = bw_qs.count() + ds_qs.count() + pf_qs.count()
        today_ops = bw_today.count() + ds_today.count() + pf_today.count()

        total_water_loss = (
            (bw_qs.aggregate(s=Sum("water_lost_m3"))["s"] or Decimal(0))
            + (ds_qs.aggregate(s=Sum("water_lost_m3"))["s"] or Decimal(0))
            + (pf_qs.aggregate(s=Sum("water_lost_m3"))["s"] or Decimal(0))
        )

        today_water_loss = (
            (bw_today.aggregate(s=Sum("water_lost_m3"))["s"] or Decimal(0))
            + (ds_today.aggregate(s=Sum("water_lost_m3"))["s"] or Decimal(0))
            + (pf_today.aggregate(s=Sum("water_lost_m3"))["s"] or Decimal(0))
        )

        completed = bw_qs.filter(status__name="completed").count()
        completion_rate = round((completed / bw_qs.count()) * 100, 1) if bw_qs.count() else 0

        return [
            {"label": "Total Operations", "value": total_ops, "icon": "fa-arrows-rotate", "color": "cyan"},
            {"label": "Today's Ops", "value": today_ops, "icon": "fa-calendar-day", "color": "emerald"},
            {"label": "Water Loss (m³)", "value": f"{total_water_loss:.1f}", "icon": "fa-droplet", "color": "rose"},
            {"label": "Today Loss (m³)", "value": f"{today_water_loss:.1f}", "icon": "fa-water", "color": "amber"},
            {"label": "Backwashes", "value": bw_qs.count(), "icon": "fa-filter", "color": "blue"},
            {"label": "Desludging", "value": ds_qs.count(), "icon": "fa-broom", "color": "purple"},
            {"label": "Pump Flush", "value": pf_qs.count(), "icon": "fa-pump-medical", "color": "slate"},
            {"label": "Completion %", "value": f"{completion_rate}%", "icon": "fa-check-circle", "color": "emerald"},
        ]

    # ─── Daily Trend ───
    def _build_daily_trend(self, qs, start_date, today):
        daily = (
            qs.values("start_time__date")
            .annotate(count=Count("id"))
            .order_by("start_time__date")
        )
        return {
            "labels": [str(d["start_time__date"]) for d in daily],
            "data": [d["count"] for d in daily],
        }

    # ─── Water Loss Trend ───
    def _build_water_loss_trend(self, bw_qs, ds_qs, pf_qs, start_date, today):
        loss_by_day = defaultdict(float)
        for qs in [bw_qs, ds_qs, pf_qs]:
            for row in qs.values("start_time__date").annotate(loss=Sum("water_lost_m3")).order_by("start_time__date"):
                loss_by_day[str(row["start_time__date"])] += float(row["loss"] or 0)

        sorted_days = sorted(loss_by_day.keys())
        return {
            "labels": sorted_days,
            "data": [round(loss_by_day[d], 2) for d in sorted_days],
        }

    # ─── Status Distribution ───
    def _build_status_distribution(self, bw_qs):
        dist = bw_qs.values("status__name").annotate(count=Count("id")).order_by("-count")
        return {
            "labels": [d["status__name"] or "Unknown" for d in dist],
            "data": [d["count"] for d in dist],
        }

    # ─── Filter Utilization ───
    def _build_filter_utilization(self, bw_qs):
        util = (
            bw_qs.values("filter_unit__name")
            .annotate(
                count=Count("id"),
                total_loss=Sum("water_lost_m3"),
            )
            .order_by("-count")[:12]
        )
        return {
            "labels": [u["filter_unit__name"] or "—" for u in util],
            "counts": [u["count"] for u in util],
            "losses": [float(u["total_loss"] or 0) for u in util],
        }

    # ─── Recent Operations ───
    def _build_recent_ops(self, bw_qs, ds_qs, pf_qs):
        ops = []
        for bw in bw_qs.select_related("filter_unit", "performed_by", "status")[:8]:
            ops.append({
                "type": "Backwash",
                "target": str(bw.filter_unit) if bw.filter_unit else "—",
                "operator": str(bw.performed_by) if bw.performed_by else "—",
                "status": str(bw.status) if bw.status else "—",
                "duration": bw.duration_minutes,
                "loss_m3": float(bw.water_lost_m3 or 0),
                "time": bw.start_time.isoformat(),
            })
        for ds in ds_qs.select_related("clarifier", "performed_by", "status")[:5]:
            ops.append({
                "type": "Desludge",
                "target": str(ds.clarifier) if ds.clarifier else "—",
                "operator": str(ds.performed_by) if ds.performed_by else "—",
                "status": str(ds.status) if ds.status else "—",
                "duration": ds.duration_minutes,
                "loss_m3": float(ds.water_lost_m3 or 0),
                "time": ds.start_time.isoformat(),
            })
        for pf in pf_qs.select_related("chemical_pump", "performed_by", "status")[:5]:
            ops.append({
                "type": "Flush",
                "target": str(pf.chemical_pump) if pf.chemical_pump else "—",
                "operator": str(pf.performed_by) if pf.performed_by else "—",
                "status": str(pf.status) if pf.status else "—",
                "duration": pf.duration_minutes,
                "loss_m3": float(pf.water_lost_m3 or 0),
                "time": pf.start_time.isoformat(),
            })
        ops.sort(key=lambda x: x["time"], reverse=True)
        return ops[:15]

    # ─── Operator Stats ───
    def _build_operator_stats(self, bw_qs, ds_qs, pf_qs):
        stats = defaultdict(lambda: {"ops": 0, "total_loss": 0.0})
        for qs in [bw_qs, ds_qs, pf_qs]:
            for row in qs.values("performed_by__username").annotate(
                count=Count("id"), loss=Sum("water_lost_m3")
            ):
                name = row["performed_by__username"] or "Unknown"
                stats[name]["ops"] += row["count"]
                stats[name]["total_loss"] += float(row["loss"] or 0)

        return sorted(
            [{"operator": k, **v} for k, v in stats.items()],
            key=lambda x: x["ops"],
            reverse=True,
        )[:10]

    # ─── Duration Analytics ───
    def _build_duration_stats(self, bw_qs, ds_qs, pf_qs):
        result = {}
        for label, qs in [("backwash", bw_qs), ("desludge", ds_qs), ("flush", pf_qs)]:
            completed = qs.filter(end_time__isnull=False)
            durations = []
            for op in completed:
                d = op.duration_minutes
                if d is not None and d > 0:
                    durations.append(d)
            if durations:
                result[label] = {
                    "avg": round(sum(durations) / len(durations), 1),
                    "min": min(durations),
                    "max": max(durations),
                    "count": len(durations),
                }
            else:
                result[label] = {"avg": 0, "min": 0, "max": 0, "count": 0}
        return result
