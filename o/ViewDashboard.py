"""
o/ViewDashboard.py — Chemical Operations Advanced Cockpit
Data-driven dashboard for chemical dosing, pump status, tank levels, and stock.
"""
import json
import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Avg, Count, Sum, F
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View

from core.mixins import WanjalaMixin
from core.registry import registry

from .models import (
    ChemicalPump, PumpStatus, ChemicalTank, ChemicalStock,
    CoagulantUsageRecord, PHAdjusterUsageRecord,
    DisinfectantUsageRecord, FlocculantUsageRecord,
    ChemicalUsageRecord,
)

logger = logging.getLogger(__name__)


class DashboardView(WanjalaMixin, View):
    """
    Advanced cockpit for Chemical Operations (dosing, pumps, tanks, stock).
    """

    template_name = "o/dashboard.html"
    app_label = "o"

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

        # Dosing records
        coag_qs = CoagulantUsageRecord.objects.filter(date__gte=start_date)
        ph_qs = PHAdjusterUsageRecord.objects.filter(date__gte=start_date)
        disinf_qs = DisinfectantUsageRecord.objects.filter(date__gte=start_date)
        flocc_qs = FlocculantUsageRecord.objects.filter(date__gte=start_date)

        usage_qs = ChemicalUsageRecord.objects.filter(date_used__gte=start_date)

        # Pump status
        pumps = ChemicalPump.objects.all()
        pump_statuses = self._get_pump_statuses(pumps)

        # Tank info
        tanks = ChemicalTank.objects.all()

        # Stock levels
        stocks = ChemicalStock.objects.select_related("chemical").all()

        # KPIs
        kpis = self._build_kpis(coag_qs, ph_qs, disinf_qs, flocc_qs, pumps, stocks)

        # Usage trend
        usage_trend = self._build_usage_trend(usage_qs, start_date, today)

        # Category breakdown
        cat_breakdown = self._build_category_breakdown(coag_qs, ph_qs, disinf_qs, flocc_qs)

        # Dosage compliance (actual vs expected)
        compliance = self._build_dosage_compliance(coag_qs, ph_qs, disinf_qs)

        # Stock levels
        stock_data = self._build_stock_data(stocks)

        # Recent dosing
        recent_dosing = self._build_recent_dosing(coag_qs, ph_qs, disinf_qs, flocc_qs)

        charts_payload = {
            "usage_trend": usage_trend,
            "category_breakdown": cat_breakdown,
            "compliance": compliance,
            "stock_levels": stock_data,
            "pump_statuses": pump_statuses,
        }

        try:
            entries = registry.for_app(self.app_label) or []
        except Exception:
            entries = []

        return {
            "dashboard_title": "Chemical Operations",
            "dashboard_subtitle": f"Dosing & Stock Telemetry · {period_days}d",
            "dashboard_icon": "flask-vial",
            "app_groups": registry.sidebar(self.app_label) if entries else [],
            "kpis": kpis,
            "pump_statuses": pump_statuses,
            "recent_dosing": recent_dosing,
            "tanks": [{"name": t.name, "capacity": t.capacity_liters, "category": t.category} for t in tanks[:12]],
            "charts_json": json.dumps(charts_payload, cls=DjangoJSONEncoder, default=str),
            "dashboard_json_payload": charts_payload,
            "period_days": period_days,
        }

    def _build_kpis(self, coag_qs, ph_qs, disinf_qs, flocc_qs, pumps, stocks):
        total_records = coag_qs.count() + ph_qs.count() + disinf_qs.count() + flocc_qs.count()
        working_pumps = sum(1 for p in pumps if self._latest_pump_status(p) == "working")
        total_stock = sum(float(s.quantity_kg) for s in stocks)
        low_stock = sum(1 for s in stocks if s.quantity_kg < 50)

        return [
            {"label": "Dosing Records", "value": total_records, "icon": "fa-vial", "color": "cyan"},
            {"label": "Coagulant", "value": coag_qs.count(), "icon": "fa-droplet", "color": "blue"},
            {"label": "pH Adjuster", "value": ph_qs.count(), "icon": "fa-flask", "color": "purple"},
            {"label": "Disinfectant", "value": disinf_qs.count(), "icon": "fa-shield-virus", "color": "emerald"},
            {"label": "Flocculant", "value": flocc_qs.count(), "icon": "fa-atom", "color": "amber"},
            {"label": "Pumps Working", "value": f"{working_pumps}/{pumps.count()}", "icon": "fa-pump-medical", "color": "emerald"},
            {"label": "Total Stock (kg)", "value": f"{total_stock:.0f}", "icon": "fa-warehouse", "color": "cyan"},
            {"label": "Low Stock Alerts", "value": low_stock, "icon": "fa-triangle-exclamation", "color": "rose"},
        ]

    def _get_pump_statuses(self, pumps):
        result = []
        for p in pumps[:15]:
            latest = PumpStatus.objects.filter(pump=p).order_by("-created_at").first()
            result.append({
                "name": p.name,
                "status": latest.status if latest else "unknown",
                "category": p.category,
            })
        return result

    def _latest_pump_status(self, pump):
        latest = PumpStatus.objects.filter(pump=pump).order_by("-created_at").first()
        return latest.status if latest else "unknown"

    def _build_usage_trend(self, usage_qs, start_date, today):
        daily = (
            usage_qs.values("date_used")
            .annotate(total=Sum("quantity_used_kg"))
            .order_by("date_used")
        )
        return {
            "labels": [str(d["date_used"]) for d in daily],
            "data": [round(float(d["total"] or 0), 1) for d in daily],
        }

    def _build_category_breakdown(self, coag_qs, ph_qs, disinf_qs, flocc_qs):
        return {
            "labels": ["Coagulant", "pH Adjuster", "Disinfectant", "Flocculant"],
            "data": [coag_qs.count(), ph_qs.count(), disinf_qs.count(), flocc_qs.count()],
        }

    def _build_dosage_compliance(self, coag_qs, ph_qs, disinf_qs):
        compliant = 0
        total = 0
        for qs in [coag_qs, ph_qs, disinf_qs]:
            for rec in qs.filter(expected_dosage__isnull=False):
                total += 1
                if rec.expected_dosage and rec.actual_dosage:
                    deviation = abs(rec.actual_dosage - rec.expected_dosage) / rec.expected_dosage
                    if deviation <= 0.15:
                        compliant += 1
        rate = round((compliant / total) * 100, 1) if total else 0
        return {"compliant": compliant, "total": total, "rate": rate}

    def _build_stock_data(self, stocks):
        return {
            "labels": [s.chemical.name for s in stocks[:12]],
            "data": [float(s.quantity_kg) for s in stocks[:12]],
        }

    def _build_recent_dosing(self, coag_qs, ph_qs, disinf_qs, flocc_qs):
        ops = []
        for rec in coag_qs.select_related("chemical", "recorded_by")[:5]:
            ops.append({
                "type": "Coagulant", "chemical": str(rec.chemical),
                "dosage": rec.actual_dosage, "expected": rec.expected_dosage,
                "flow": rec.raw_water_flow_rate, "date": str(rec.date),
                "operator": str(rec.recorded_by or "—"),
            })
        for rec in ph_qs.select_related("chemical", "recorded_by")[:5]:
            ops.append({
                "type": "pH Adj", "chemical": str(rec.chemical),
                "dosage": rec.actual_dosage, "expected": rec.expected_dosage,
                "flow": rec.raw_water_flow_rate, "date": str(rec.date),
                "operator": str(rec.recorded_by or "—"),
            })
        for rec in disinf_qs.select_related("chemical", "recorded_by")[:3]:
            ops.append({
                "type": "Disinfect", "chemical": str(rec.chemical),
                "dosage": rec.actual_dosage, "expected": rec.expected_dosage,
                "flow": rec.raw_water_flow_rate, "date": str(rec.date),
                "operator": str(rec.recorded_by or "—"),
            })
        for rec in flocc_qs.select_related("chemical", "recorded_by")[:3]:
            ops.append({
                "type": "Floccul", "chemical": str(rec.chemical),
                "dosage": rec.actual_dosage, "expected": rec.expected_dosage,
                "flow": rec.raw_water_flow_rate, "date": str(rec.date),
                "operator": str(rec.recorded_by or "—"),
            })
        ops.sort(key=lambda x: x["date"], reverse=True)
        return ops[:15]
