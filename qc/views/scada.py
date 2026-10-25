from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal

from django.shortcuts import render
from django.utils import timezone
from django.views import View

from core.mixins import WanjalaMixin
from t.models import TreatmentPlant
from qc.services.scada_dashboard_service import SCADADashboardService


logger = logging.getLogger(__name__)


class SCADADashboardView(WanjalaMixin, View):
    """
    Unified SCADA Quality Control & Sensor Telemetry Command Center.

    Combines automated field sensor telemetry (instruments app) with
    laboratory QC manual analytical entry worksheets (qc/results/cards)
    into a single multi-tabbed, cyber-industrial monitoring dashboard.
    """

    template_name = "qc/scada_dashboard.html"

    def get(self, request):
        plant = self._resolve_plant(request)
        selected_date = self._resolve_date(request)
        active_tab = request.GET.get("tab", "overview")

        service = SCADADashboardService(plant=plant, selected_date=selected_date, user=request.user)
        ctx = service.build_unified_scada_context(active_tab=active_tab)

        # Build chart data payloads for Trend Analytics tab
        ctx.update(self._build_chart_payloads(ctx))

        return render(request, self.template_name, ctx)

    # ------------------------------------------------------------------
    #  Plant & Date Resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_plant(request):
        """Resolve the plant from the request GET parameters."""
        plant_pk = request.GET.get("plant")
        if plant_pk:
            try:
                return TreatmentPlant.objects.get(pk=plant_pk)
            except (TreatmentPlant.DoesNotExist, ValueError):
                pass
        # Fallback: first available plant
        return TreatmentPlant.objects.order_by("name").first()

    @staticmethod
    def _resolve_date(request):
        """Resolve the selected date from the request GET parameters."""
        date_str = request.GET.get("date")
        if date_str:
            try:
                return date.fromisoformat(date_str)
            except (ValueError, TypeError):
                pass
        return timezone.localdate()

    # ------------------------------------------------------------------
    #  Chart Data Construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_chart_payloads(ctx):
        """
        Construct JSON-serializable chart data payloads for the
        Trend Analytics tab (Chart.js).
        """
        stages = ctx.get("stages", [])

        # 1. Stage Concordance Bar Chart
        concordance_data = {
            "labels": [],
            "synch": [],
            "drift": [],
            "critical": [],
        }
        for stage in stages:
            concordance_data["labels"].append(stage.stage_title)
            concordance_data["synch"].append(stage.in_synch_count)
            concordance_data["drift"].append(stage.drift_count)
            concordance_data["critical"].append(stage.critical_count)

        # 2. Variance Distribution Radar
        radar_data = {"labels": [], "values": []}
        for stage in stages:
            radar_data["labels"].append(stage.stage_title)
            variances = [
                c.pct_variance
                for c in stage.comparisons
                if c.pct_variance is not None
            ]
            avg_var = sum(variances) / len(variances) if variances else 0
            radar_data["values"].append(round(avg_var, 1))

        # 3. Health Score Doughnut
        health_data = {"score": ctx.get("scada_health_index", 100)}

        # 4. Parameter Deviation Bubble Chart
        bubble_datasets = []
        for stage in stages:
            points = []
            for comp in stage.comparisons:
                if comp.delta_abs is not None and comp.pct_variance is not None:
                    radius = 5
                    if comp.reconciliation_status == "critical_mismatch":
                        radius = 12
                    elif comp.reconciliation_status == "minor_drift":
                        radius = 8

                    points.append({
                        "x": float(comp.delta_abs),
                        "y": float(comp.pct_variance),
                        "r": radius,
                        "label": f"{comp.parameter_name} ({comp.phase_name})",
                    })

            if points:
                # Choose color based on stage health
                color = "#10b981"
                if any(p["r"] >= 12 for p in points):
                    color = "#ef4444"
                elif any(p["r"] >= 8 for p in points):
                    color = "#f59e0b"

                bubble_datasets.append({
                    "label": stage.stage_title,
                    "data": points,
                    "backgroundColor": f"{color}88",
                    "borderColor": color,
                    "borderWidth": 1,
                })

        bubble_data = {"datasets": bubble_datasets}

        return {
            "chart_concordance_data": json.dumps(concordance_data),
            "chart_radar_data": json.dumps(radar_data),
            "chart_health_data": json.dumps(health_data),
            "chart_bubble_data": json.dumps(bubble_data),
        }
