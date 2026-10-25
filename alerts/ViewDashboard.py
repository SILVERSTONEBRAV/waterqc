"""Plant-scoped operational dashboard for configured alerts and alert states."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View

from core.engine.super_user import SuperUserEngine
from core.mixins import WanjalaMixin
from core.registry import registry
from t.models import TreatmentPlant

from .models import AlertConfig, AlertState

logger = logging.getLogger(__name__)


class DashboardView(WanjalaMixin, View):
    """Show alert lifecycle data from AlertState, scoped to user and plant."""

    template_name = "alerts/dashboard.html"
    app_label = "alerts"
    permission_required_view = "alerts.view_alertstate"

    def get(self, request):
        if response := self.process_request(request):
            return response
        if not SuperUserEngine.is_superuser(request.user) and not request.user.has_perm(
            self.permission_required_view
        ):
            raise PermissionDenied("Permission 'alerts.view_alertstate' is required.")
        self.check_idle_timeout()

        context = self.get_context(request)
        wants_json = (
            "application/json" in request.headers.get("Accept", "")
            or request.GET.get("format") == "json"
        )
        if wants_json:
            return JsonResponse(context["dashboard_json_payload"])
        return HttpResponse(render_to_string(self.template_name, context, request=request))

    def get_context(self, request):
        period_days = self._period_days(request.GET.get("days", 30))
        is_superuser = SuperUserEngine.is_superuser(request.user)
        plant = self._resolve_plant(request, is_superuser)
        start_at = timezone.now() - timedelta(days=period_days)

        states = AlertState.objects.select_related(
            "alert_config",
            "alert_config__template",
            "alert_config__category",
        )
        if not is_superuser:
            from ca.services.alerts_service import ChemicalAlertsService

            allowed_alert_types = [
                value
                for value in AlertConfig.objects.values_list("alert_type", flat=True).distinct()
                if ChemicalAlertsService._can_view_alert_type(
                    request.user,
                    value,
                    is_superuser=False,
                )
            ]
            states = states.filter(alert_config__alert_type__in=allowed_alert_types)
        if plant is not None:
            plant_scope = (
                Q(geo_context__plant_id=str(plant.pk))
                | Q(alert_config__geo_context__plant_id=str(plant.pk))
                | Q(alert_config__target_treatment_plants=plant)
            )
            if not is_superuser:
                audience = Q(alert_config__recipients=request.user) | Q(
                    alert_config__target_groups__in=request.user.groups.all()
                )
                if getattr(request.user, "section_id", None):
                    audience |= Q(alert_config__target_sections__pk=request.user.section_id)
                targeted_to_plant = Q(alert_config__target_treatment_plants=plant)
                unscoped_but_addressed = (
                    Q(alert_config__target_treatment_plants__isnull=True) & audience
                )
                plant_scope &= targeted_to_plant | unscoped_but_addressed
            states = states.filter(plant_scope)
        elif not is_superuser:
            states = states.none()

        states = states.distinct()
        window_states = states.filter(updated_at__gte=start_at)
        total_count = window_states.count()
        acknowledged_count = window_states.filter(
            state__in=(AlertState.StateChoices.ACKNOWLEDGED, AlertState.StateChoices.VERIFIED)
        ).count()
        active_count = window_states.filter(
            state__in=(
                AlertState.StateChoices.QUEUED,
                AlertState.StateChoices.SENT,
                AlertState.StateChoices.ESCALATED,
            )
        ).count()
        ack_rate = round(acknowledged_count / total_count * 100, 1) if total_count else 0

        by_severity = list(
            window_states.values("alert_config__priority")
            .annotate(count=Count("pk", distinct=True))
            .order_by("alert_config__priority")
        )
        by_state = list(
            window_states.values("state")
            .annotate(count=Count("pk", distinct=True))
            .order_by("state")
        )
        daily = list(
            window_states.values("updated_at__date")
            .annotate(count=Count("pk", distinct=True))
            .order_by("updated_at__date")
        )

        configs = AlertConfig.objects.filter(active=True)
        if not is_superuser:
            configs = configs.filter(alert_type__in=allowed_alert_types)
        if plant is not None:
            if is_superuser:
                configs = configs.filter(
                    Q(target_treatment_plants=plant)
                    | Q(target_treatment_plants__isnull=True)
                )
            else:
                config_audience = Q(recipients=request.user) | Q(
                    target_groups__in=request.user.groups.all()
                )
                if getattr(request.user, "section_id", None):
                    config_audience |= Q(target_sections__pk=request.user.section_id)
                configs = configs.filter(
                    Q(target_treatment_plants=plant)
                    | (Q(target_treatment_plants__isnull=True) & config_audience)
                )
        elif not is_superuser:
            configs = configs.none()

        kpis = [
            {"label": "Alert events", "value": total_count, "icon": "fa-bell", "color": "cyan"},
            {"label": "Active", "value": active_count, "icon": "fa-bell-on", "color": "rose"},
            {"label": "Acknowledged", "value": acknowledged_count, "icon": "fa-check-double", "color": "blue"},
            {"label": "Ack rate", "value": f"{ack_rate}%", "icon": "fa-chart-simple", "color": "emerald"},
            {"label": "Active rules", "value": configs.distinct().count(), "icon": "fa-gear", "color": "purple"},
        ]

        recent = []
        for item in window_states.order_by("-updated_at", "-pk")[:15]:
            config = item.alert_config
            recent.append({
                "message": f"{(config.get_alert_type_display() if config else 'Alert')} · Ref {item.instance_ref}"[:120],
                "severity": config.priority if config else "medium",
                "state": item.get_state_display(),
                "time": timezone.localtime(item.updated_at).strftime("%Y-%m-%d %H:%M"),
            })

        charts_payload = {
            "daily_trend": {
                "labels": [str(row["updated_at__date"]) for row in daily],
                "data": [row["count"] for row in daily],
            },
            "by_severity": {
                "labels": [row["alert_config__priority"] or "unknown" for row in by_severity],
                "data": [row["count"] for row in by_severity],
            },
            "by_state": {
                "labels": [row["state"] for row in by_state],
                "data": [row["count"] for row in by_state],
            },
            "ack_split": {
                "labels": ["Acknowledged", "Active or other"],
                "data": [acknowledged_count, max(total_count - acknowledged_count, 0)],
            },
        }
        try:
            entries = registry.for_app(self.app_label) or []
        except Exception:
            entries = []

        return {
            "dashboard_title": "Alert Center",
            "dashboard_subtitle": f"Plant-scoped alert lifecycle · {period_days}d",
            "dashboard_icon": "bell",
            "app_groups": registry.sidebar(self.app_label) if entries else [],
            "plant": plant,
            "kpis": kpis,
            "recent_alerts": recent,
            "charts_json": json.dumps(charts_payload, cls=DjangoJSONEncoder, default=str),
            "dashboard_json_payload": charts_payload,
            "period_days": period_days,
        }

    @staticmethod
    def _period_days(value):
        try:
            return max(1, min(int(value), 365))
        except (TypeError, ValueError):
            return 30

    @staticmethod
    def _resolve_plant(request, is_superuser):
        if not is_superuser:
            plant = getattr(request.user, "assigned_treatment_plant", None)
            requested = request.GET.get("plant")
            if requested and str(getattr(plant, "pk", "")) != str(requested):
                raise PermissionDenied("Alert scope is outside your assigned treatment plant.")
            return plant

        requested = request.GET.get("plant") or next(
            (
                request.session.get(key)
                for key in (
                    "ca_selected_plant",
                    "qc_selected_plant",
                    "selected_plant_id",
                    "selected_treatment_plant_id",
                    "active_plant_id",
                    "plant_id",
                    "treatment_plant_id",
                )
                if request.session.get(key)
            ),
            None,
        )
        if not requested or str(requested).casefold() in {"all", "none"}:
            return None
        if not str(requested).isdigit():
            raise Http404("Treatment plant not found.")
        try:
            return TreatmentPlant.objects.get(pk=int(requested))
        except TreatmentPlant.DoesNotExist as exc:
            raise Http404("Treatment plant not found.") from exc
