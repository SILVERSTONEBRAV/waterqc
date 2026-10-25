from __future__ import annotations

import logging
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from core.mixins import WanjalaMixin
from instruments.services.telemetry_dashboard_service import TelemetryDashboardService
from t.models import TreatmentPlant

logger = logging.getLogger(__name__)


class InstrumentTelemetryDashboardView(WanjalaMixin, View):
    """
    Treatment-Plant Scoped Real-Time Telemetry Dashboard for Instruments.
    Presents a read-only tabular matrix of live sensor streams grouped by stage
    and phase, with automated HTMX partial refreshes.
    """

    template_name = "instruments/telemetry_dashboard.html"
    partial_grid_template = "instruments/partials/_telemetry_cards.html"
    partial_topbar_template = "instruments/partials/_telemetry_topbar.html"

    def get_plant(self, request, plants):
        plant_id = request.GET.get("plant")
        if plant_id:
            plant = plants.filter(pk=plant_id).first()
            if plant:
                return plant

        # Fallback to user treatment plant if assigned
        user_plant = getattr(request.user, "treatment_plant", None)
        if user_plant and user_plant in plants:
            return user_plant

        return plants.first()

    def get(self, request, *args, **kwargs):
        plants = TreatmentPlant.objects.all().order_by("name")
        selected_plant = self.get_plant(request, plants)

        service = TelemetryDashboardService(plant=selected_plant)
        stage_groups = service.build_telemetry_matrix()
        kpis = service.get_kpis()

        context = {
            "plants": plants,
            "selected_plant": selected_plant,
            "plant": selected_plant,
            "stage_groups": stage_groups,
            "kpis": kpis,
            "is_qca_insights_page": True,
            "last_synced": timezone.now(),
        }

        # HTMX partial updates for live polling
        if request.headers.get("HX-Request"):
            partial = request.GET.get("partial")
            if partial == "grid":
                return render(request, self.partial_grid_template, context)
            elif partial == "topbar":
                return render(request, self.partial_topbar_template, context)

        return render(request, self.template_name, context)
