# maintenance/ViewDashboard.py — permission and plant scoped command center
from __future__ import annotations

import logging
from datetime import date, timedelta
from statistics import median

from django.db.models import Case, Count, F, Q, Sum, Value, When
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View

from core.mixins import WanjalaMixin
from core.registry import registry

logger = logging.getLogger(__name__)


class DashboardView(WanjalaMixin, View):
    """Unified, user-scoped Maintenance operations dashboard."""

    template_name = "maintenance/dashboard.html"
    app_label = "maintenance"

    def get(self, request):
        if (response := self.process_request(request)):
            return response
        self.check_idle_timeout()
        context = self.get_context(request)

        if request.GET.get("export") == "csv":
            return self.export_csv(context, request.GET.get("tab", "overview"))

        response = HttpResponse(
            render_to_string(self.template_name, context, request=request)
        )
        response["Cache-Control"] = "private, no-store"
        return response

    @staticmethod
    def _has_perm(user, model, action="view"):
        permission = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
        return bool(user.is_superuser or user.has_perm(permission))

    @staticmethod
    def _month_start(offset=0):
        now = timezone.localdate()
        month_index = now.year * 12 + now.month - 1 + offset
        year, month_zero = divmod(month_index, 12)
        return date(year, month_zero + 1, 1)

    def get_context(self, request):
        # Import through the Maintenance facade so the dashboards share one
        # registered set of domain model classes and database records.
        from maintenance.models import (
            DutyHouse,
            DutyHouseOccupancy,
            DutyHouseUnit,
            IncidentSeverity,
            IncidentStatus,
            IncidentStream,
            IncidentType,
            Location,
            MaintenanceIncident,
            OrderStatus,
            RequestStatus,
            SLARecord,
            SLAStatus,
            WorkOrder,
            WorkRequest,
            OccupancyTransfer,
        )
        from t.models import TreatmentPlant

        user = request.user
        can_view_housing = self._has_perm(user, DutyHouse)
        can_view_units = self._has_perm(user, DutyHouseUnit)
        can_view_occupants = self._has_perm(user, DutyHouseOccupancy)
        can_add_occupants = self._has_perm(user, DutyHouseOccupancy, "add")
        can_change_occupants = self._has_perm(user, DutyHouseOccupancy, "change")
        can_transfer_occupants = (
            can_view_occupants
            and can_view_units
            and can_change_occupants
            and self._has_perm(user, OccupancyTransfer, "add")
        )
        can_view_incidents = self._has_perm(user, MaintenanceIncident)
        can_add_incidents = self._has_perm(user, MaintenanceIncident, "add")
        can_view_requests = self._has_perm(user, WorkRequest)
        can_view_orders = self._has_perm(user, WorkOrder)
        can_view_sla = self._has_perm(user, SLARecord)
        can_access_dashboard = any(
            (
                can_view_housing,
                can_view_incidents,
                can_add_incidents,
                can_view_requests,
                can_view_orders,
                can_view_sla,
            )
        )

        all_user_plants = (
            TreatmentPlant.objects.all()
            if user.is_superuser
            else TreatmentPlant.objects.filter(assigned_users=user)
        ).order_by("name")
        requested_plant = (request.GET.get("plant") or "").strip()
        invalid_plant = False
        if user.is_superuser:
            if requested_plant:
                selected_plant = all_user_plants.filter(pk=requested_plant).first()
                if selected_plant is None:
                    invalid_plant = True
                    allowed_plant_ids = []
                else:
                    allowed_plant_ids = [selected_plant.pk]
            else:
                selected_plant = None
                allowed_plant_ids = None
        else:
            plant_ids = list(all_user_plants.values_list("pk", flat=True))
            if requested_plant:
                try:
                    requested_pk = int(requested_plant)
                except (TypeError, ValueError):
                    requested_pk = None
                if requested_pk not in plant_ids:
                    invalid_plant = True
                    allowed_plant_ids = []
                else:
                    allowed_plant_ids = [requested_pk]
            else:
                allowed_plant_ids = plant_ids
            selected_plant = (
                all_user_plants.filter(pk=allowed_plant_ids[0]).first()
                if len(allowed_plant_ids) == 1
                else None
            )

        tab = request.GET.get("tab", "overview")
        tab_permissions = {
            "requests": can_view_requests,
            "orders": can_view_orders,
            "incidents": can_view_incidents,
            "housing": can_view_housing,
            "sla": can_view_sla,
            "schedule": can_view_sla,
        }
        dashboard_notice = ""
        if tab in tab_permissions and not tab_permissions[tab]:
            tab = "overview"
            dashboard_notice = "You do not have permission to view that section."
        if tab not in {"overview", *tab_permissions}:
            tab = "overview"

        requests_qs = WorkRequest.objects.select_related(
            "reported_by", "duty_house", "approved_by"
        )
        orders_qs = WorkOrder.objects.select_related(
            "request", "duty_house", "assigned_to"
        )
        incidents_qs = MaintenanceIncident.objects.select_related(
            "plant", "duty_house", "equipment", "reported_by", "assigned_to", "cluster"
        )
        houses_qs = DutyHouse.objects.select_related("plant", "location")
        sla_qs = SLARecord.objects.select_related("request", "request__duty_house")
        units_qs = DutyHouseUnit.objects.select_related("duty_house")
        occupancy_qs = DutyHouseOccupancy.objects.select_related(
            "duty_house", "unit", "user"
        )

        # An empty authorized plant list means no records. Unlinked requests and
        # orders are only visible to superusers because they cannot be scoped.
        if allowed_plant_ids is not None:
            requests_qs = requests_qs.filter(
                duty_house__plant_id__in=allowed_plant_ids
            )
            orders_qs = orders_qs.filter(
                Q(duty_house__plant_id__in=allowed_plant_ids)
                | Q(
                    duty_house__isnull=True,
                    request__duty_house__plant_id__in=allowed_plant_ids,
                )
            )
            incidents_qs = incidents_qs.filter(
                (
                    Q(plant_id__in=allowed_plant_ids)
                    & (
                        Q(duty_house__isnull=True)
                        | Q(duty_house__plant_id__in=allowed_plant_ids)
                    )
                )
                | Q(plant__isnull=True, duty_house__plant_id__in=allowed_plant_ids)
            )
            houses_qs = houses_qs.filter(plant_id__in=allowed_plant_ids)
            units_qs = units_qs.filter(duty_house__plant_id__in=allowed_plant_ids)
            occupancy_qs = occupancy_qs.filter(
                duty_house__plant_id__in=allowed_plant_ids
            )
            sla_qs = sla_qs.filter(
                request__duty_house__plant_id__in=allowed_plant_ids
            )

        if not can_view_requests:
            requests_qs = requests_qs.none()
        if not can_view_orders:
            orders_qs = orders_qs.none()
        if not can_view_incidents:
            incidents_qs = incidents_qs.none()
        if not can_view_housing:
            houses_qs = houses_qs.none()
            units_qs = units_qs.none()
            occupancy_qs = occupancy_qs.none()
        elif not can_view_occupants:
            # Aggregated occupancy remains available to housing viewers, while
            # personal occupant names and records are withheld.
            occupancy_qs = occupancy_qs.none()
        if not can_view_units:
            units_qs = units_qs.none()
        if not can_view_sla:
            sla_qs = sla_qs.none()

        now = timezone.now()
        open_request_statuses = [
            RequestStatus.DRAFT,
            RequestStatus.PENDING,
            RequestStatus.APPROVED,
        ]
        active_order_statuses = [
            OrderStatus.QUEUED,
            OrderStatus.ASSIGNED,
            OrderStatus.IN_PROGRESS,
            OrderStatus.ON_HOLD,
        ]
        open_incident_statuses = [
            IncidentStatus.REPORTED,
            IncidentStatus.UNDER_REVIEW,
            IncidentStatus.CONFIRMED,
            IncidentStatus.ESCALATED,
            IncidentStatus.AUTO_DISPATCHED,
        ]

        open_requests = requests_qs.filter(status__in=open_request_statuses)
        active_orders = orders_qs.filter(status__in=active_order_statuses)
        open_incidents = incidents_qs.filter(status__in=open_incident_statuses)
        breached_sla = sla_qs.filter(status=SLAStatus.BREACHED)
        active_sla = sla_qs.filter(status=SLAStatus.ACTIVE)
        due_soon = active_sla.filter(
            resolution_due__lte=now + timedelta(hours=8), resolution_due__gte=now
        )

        # Capacity occupancy is based on occupied places / configured capacity,
        # not occupied unit records / unit count.
        occupied_units_qs = units_qs.annotate(
            current_occupants=Count(
                "occupancies", filter=Q(occupancies__is_current=True)
            )
        )
        unit_metrics = list(
            occupied_units_qs.values_list(
                "max_occupants", "current_occupants", "status"
            )
        )
        total_units = len(unit_metrics)
        total_capacity = sum(capacity for capacity, _, _ in unit_metrics)
        current_occupants = (
            sum(occupants for _, occupants, _ in unit_metrics)
            if can_view_occupants
            else 0
        )
        occupied_unit_count = sum(
            1 for _, _, status in unit_metrics if status == "occupied"
        )
        over_capacity_count = (
            sum(1 for capacity, occupants, _ in unit_metrics if occupants > capacity)
            if can_view_occupants
            else 0
        )
        occupancy_rate = (
            round((current_occupants / total_capacity) * 100, 1)
            if total_capacity and can_view_occupants
            else 0
        )

        # House filters and summary bars operate only on records the user may see.
        house_search = (request.GET.get("house_q") or "").strip()[:100]
        house_status = request.GET.get("house_status", "")
        house_location = request.GET.get("location", "")
        houses_base = houses_qs
        if house_search:
            houses_base = houses_base.filter(
                Q(house_number__icontains=house_search)
                | Q(name__icontains=house_search)
                | Q(location__name__icontains=house_search)
            )
        if house_status in {choice[0] for choice in DutyHouse._meta.get_field("status").choices}:
            houses_base = houses_base.filter(status=house_status)
        if house_location:
            houses_base = houses_base.filter(location_id=house_location)

        house_rows = list(
            houses_base.annotate(
                unit_count=(Count("units", distinct=True) if can_view_units else Value(0)),
                current_occupant_count=Count(
                    "occupancies",
                    filter=Q(occupancies__is_current=True),
                    distinct=True,
                ) if can_view_occupants else Value(0),
                open_incident_count=(
                    Count(
                        "incidents",
                        filter=(
                            Q(incidents__status__in=open_incident_statuses)
                            & (
                                Q(incidents__plant__isnull=True)
                                | Q(incidents__plant_id=F("plant_id"))
                            )
                        ),
                        distinct=True,
                    ) if can_view_incidents else Value(0)
                ),
            ).order_by("location__name", "house_number")[:100]
        )
        capacity_by_house = dict(
            units_qs.values("duty_house_id")
            .annotate(capacity=Sum("max_occupants"))
            .values_list("duty_house_id", "capacity")
        ) if can_view_units else {}
        for house in house_rows:
            house.occupant_capacity = capacity_by_house.get(house.pk, 0) or 0

        house_status_counts = dict(
            houses_qs.values("status").annotate(total=Count("pk")).values_list(
                "status", "total"
            )
        )
        house_status_bars = []
        max_house_status = max(house_status_counts.values(), default=1) or 1
        for value, label in DutyHouse._meta.get_field("status").choices:
            count = house_status_counts.get(value, 0)
            house_status_bars.append(
                {"label": label, "value": count, "width": round(count * 100 / max_house_status)}
            )

        location_rows = list(
            Location.objects.filter(duty_houses__in=houses_qs)
            .values("name")
            .annotate(total=Count("duty_houses", distinct=True))
            .order_by("-total", "name")[:8]
        ) if can_view_housing else []
        max_location_count = max((row["total"] for row in location_rows), default=1) or 1
        for row in location_rows:
            row["width"] = round(row["total"] * 100 / max_location_count)

        location_options = Location.objects.filter(duty_houses__in=houses_qs).distinct().order_by("name") if can_view_housing else Location.objects.none()
        incident_report_houses = (
            houses_qs.order_by("location__name", "house_number")
            if can_add_incidents and can_view_housing
            else DutyHouse.objects.none()
        )
        selected_house = None
        selected_house_id = request.GET.get("house_id")
        if selected_house_id and can_view_housing:
            selected_house = houses_qs.filter(pk=selected_house_id).first()
        house_detail_units = []
        house_detail_occupancies = []
        house_detail_incidents = []
        house_detail_orders = []
        house_detail_users = []
        house_detail_current_occupancies = []
        house_checkin_units = []
        house_detail_transfer_units = []
        if selected_house:
            house_detail_units = list(
                units_qs.filter(duty_house=selected_house)
                .annotate(
                    current_occupants=Count(
                        "occupancies", filter=Q(occupancies__is_current=True)
                    )
                )
                .prefetch_related("occupancies__user")
                .order_by("floor", "unit_number")[:300]
            )
            if (
                can_add_occupants
                and can_view_units
                and selected_house.is_active
                and selected_house.status == "active"
            ):
                house_checkin_units = [
                    unit
                    for unit in house_detail_units
                    if unit.status != "maintenance"
                    and unit.current_occupants < unit.max_occupants
                ]
            if can_view_occupants:
                house_detail_occupancies = list(
                    occupancy_qs.filter(duty_house=selected_house)
                    .order_by("-start_date")[:50]
                )
                house_detail_current_occupancies = list(
                    occupancy_qs.filter(duty_house=selected_house, is_current=True)
                    .order_by("unit__floor", "unit__unit_number")[:300]
                )
            if can_add_occupants and can_view_units:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                current_residents = DutyHouseOccupancy.objects.filter(
                    is_current=True,
                    user_id__isnull=False,
                ).values("user_id")
                house_detail_users = list(
                    User.objects.filter(
                        assigned_treatment_plant=selected_house.plant,
                        is_active=True,
                    )
                    .exclude(pk__in=current_residents)
                    .order_by("first_name", "last_name", "username")[:300]
                )
            if can_transfer_occupants:
                house_detail_transfer_units = list(
                    units_qs.filter(
                        duty_house__plant=selected_house.plant,
                        duty_house__is_active=True,
                        duty_house__status="active",
                    )
                    .exclude(status="maintenance")
                    .annotate(
                        current_occupants=Count(
                            "occupancies", filter=Q(occupancies__is_current=True)
                        )
                    )
                    .filter(current_occupants__lt=F("max_occupants"))
                    .select_related("duty_house")
                    .order_by("duty_house__house_number", "floor", "unit_number")[:300]
                )
            house_detail_incidents = list(
                incidents_qs.filter(duty_house=selected_house)
                .order_by("-reported_at")[:10]
            )
            house_detail_orders = list(
                orders_qs.filter(
                    Q(duty_house=selected_house)
                    | Q(request__duty_house=selected_house)
                ).order_by("-created_at")[:10]
            )

        # Incident queue filtering, sorting and date range are all applied after
        # plant and model permission scopes.
        incident_search = (request.GET.get("incident_q") or "").strip()[:100]
        incident_status = request.GET.get("incident_status", "")
        incident_severity = request.GET.get("severity", "")
        incident_type = request.GET.get("incident_type", "")
        incident_sort = request.GET.get("sort", "newest")
        date_from = parse_date(request.GET.get("date_from", ""))
        date_to = parse_date(request.GET.get("date_to", ""))
        incidents_base = incidents_qs
        if date_from:
            incidents_base = incidents_base.filter(reported_at__date__gte=date_from)
        if date_to:
            incidents_base = incidents_base.filter(reported_at__date__lte=date_to)
        if incident_search:
            incidents_base = incidents_base.filter(
                Q(incident_no__icontains=incident_search)
                | Q(title__icontains=incident_search)
                | Q(description__icontains=incident_search)
                | Q(equipment__name__icontains=incident_search)
                | Q(duty_house__house_number__icontains=incident_search)
            )
        valid_incident_statuses = {choice[0] for choice in IncidentStatus.choices}
        valid_severities = {choice[0] for choice in IncidentSeverity.choices}
        valid_incident_types = {choice[0] for choice in IncidentType.choices}
        if incident_status in valid_incident_statuses:
            incidents_base = incidents_base.filter(status=incident_status)
        if incident_severity in valid_severities:
            incidents_base = incidents_base.filter(severity=incident_severity)
        if incident_type in valid_incident_types:
            incidents_base = incidents_base.filter(incident_type=incident_type)
        incident_orderings = {
            "newest": ("-reported_at",),
            "oldest": ("reported_at",),
            "impact": ("-estimated_impact_score", "-reported_at"),
            "age": ("reported_at",),
        }
        if incident_sort == "severity":
            incidents_base = incidents_base.order_by(
                Case(
                    When(severity=IncidentSeverity.CRITICAL, then=Value(0)),
                    When(severity=IncidentSeverity.HIGH, then=Value(1)),
                    When(severity=IncidentSeverity.MEDIUM, then=Value(2)),
                    default=Value(3),
                ),
                "-reported_at",
            )
        else:
            incidents_base = incidents_base.order_by(
                *incident_orderings.get(incident_sort, incident_orderings["newest"])
            )
        incident_rows = list(incidents_base[:100])

        # Trends cover six months and stay bounded to authorized plants.
        trend_start = self._month_start(-5)
        monthly_rows = (
            incidents_qs.filter(reported_at__date__gte=trend_start)
            .annotate(month=TruncMonth("reported_at"))
            .values("month")
            .annotate(total=Count("pk"))
            .order_by("month")
        )
        monthly_counts = {
            (row["month"].year, row["month"].month): row["total"]
            for row in monthly_rows
            if row["month"]
        }
        incident_trend = []
        max_month = 1
        for offset in range(-5, 1):
            month_date = self._month_start(offset)
            value = monthly_counts.get((month_date.year, month_date.month), 0)
            incident_trend.append({"label": month_date.strftime("%b %Y"), "value": value})
            max_month = max(max_month, value)
        for item in incident_trend:
            item["width"] = round(item["value"] * 100 / max_month)

        severity_counts = dict(
            incidents_base.order_by().values("severity").annotate(total=Count("pk")).values_list(
                "severity", "total"
            )
        )
        max_severity = max(severity_counts.values(), default=1) or 1
        incident_severity_bars = [
            {
                "label": label,
                "value": severity_counts.get(value, 0),
                "width": round(severity_counts.get(value, 0) * 100 / max_severity),
                "tone": "rose" if value in {"critical", "high"} else "amber" if value == "medium" else "cyan",
            }
            for value, label in IncidentSeverity.choices
        ]
        incident_status_counts = dict(
            incidents_qs.values("status").annotate(total=Count("pk")).values_list(
                "status", "total"
            )
        )
        open_incident_count = sum(
            incident_status_counts.get(status, 0) for status in open_incident_statuses
        )
        critical_incident_count = incidents_qs.filter(
            status__in=open_incident_statuses, severity=IncidentSeverity.CRITICAL
        ).count()
        filtered_open_incidents = incidents_base.filter(status__in=open_incident_statuses)
        incident_age = [
            {
                "label": "Under 4 hours",
                "value": filtered_open_incidents.filter(reported_at__gte=now - timedelta(hours=4)).count(),
            },
            {
                "label": "4–24 hours",
                "value": filtered_open_incidents.filter(
                    reported_at__lt=now - timedelta(hours=4),
                    reported_at__gte=now - timedelta(hours=24),
                ).count(),
            },
            {
                "label": "1–3 days",
                "value": filtered_open_incidents.filter(
                    reported_at__lt=now - timedelta(hours=24),
                    reported_at__gte=now - timedelta(days=3),
                ).count(),
            },
            {
                "label": "Over 3 days",
                "value": filtered_open_incidents.filter(reported_at__lt=now - timedelta(days=3)).count(),
            },
        ]
        max_age = max((item["value"] for item in incident_age), default=1) or 1
        for item in incident_age:
            item["width"] = round(item["value"] * 100 / max_age)

        # Response/resolution durations are derived from recorded incident
        # events, with resolved_at used for incidents created after this field
        # was introduced. Keep the calculation bounded to the last 90 days.
        recent_report_rows = list(
            incidents_qs.filter(reported_at__gte=now - timedelta(days=90))
            .values_list("pk", "reported_at")[:3000]
        )
        recent_report_times = dict(recent_report_rows)
        first_acknowledged = {}
        first_resolved = {}
        if recent_report_times:
            for event_incident_id, event_type, event_created_at in IncidentStream.objects.filter(
                incident_id__in=recent_report_times,
                event_type__in=["acknowledged", "resolved"],
            ).order_by("created_at").values_list(
                "incident_id", "event_type", "created_at"
            )[:6000]:
                event_map_target = first_acknowledged if event_type == "acknowledged" else first_resolved
                event_map_target.setdefault(event_incident_id, event_created_at)
        response_minutes = [
            (first_acknowledged[pk] - reported_at).total_seconds() / 60
            for pk, reported_at in recent_report_rows
            if pk in first_acknowledged and first_acknowledged[pk] >= reported_at
        ]
        resolved_rows = list(
            incidents_qs.filter(
                reported_at__gte=now - timedelta(days=90), resolved_at__isnull=False
            ).values_list("pk", "resolved_at")[:3000]
        )
        resolved_times = dict(resolved_rows)
        resolved_times.update({pk: at for pk, at in first_resolved.items() if pk not in resolved_times})
        resolution_hours = [
            (resolved_at - reported_at).total_seconds() / 3600
            for pk, reported_at in recent_report_rows
            if (resolved_at := resolved_times.get(pk)) and resolved_at >= reported_at
        ]
        median_response = median(response_minutes) if response_minutes else None
        median_resolution = median(resolution_hours) if resolution_hours else None
        median_response_label = (
            f"{median_response / 60:.1f} h" if median_response is not None and median_response >= 60
            else f"{median_response:.0f} min" if median_response is not None else "—"
        )
        median_resolution_label = (
            f"{median_resolution / 24:.1f} d" if median_resolution is not None and median_resolution >= 24
            else f"{median_resolution:.1f} h" if median_resolution is not None else "—"
        )

        event_rows = IncidentStream.objects.filter(
            incident_id__in=[incident.pk for incident in incident_rows]
        ).order_by("-created_at")
        event_map = {}
        for event in event_rows:
            events = event_map.setdefault(event.incident_id, [])
            if len(events) < 5:
                events.append(event)
        for incident in incident_rows:
            incident.dashboard_events = event_map.get(incident.pk, [])

        recent_activity = self._recent_activity(
            open_requests, active_orders, open_incidents
        )
        kpis = []
        if can_view_requests:
            kpis.append({"label": "Open Requests", "value": open_requests.count(), "icon": "fa-clipboard-list", "color": "cyan"})
        if can_view_orders:
            kpis.append({"label": "Active Orders", "value": active_orders.count(), "icon": "fa-wrench", "color": "amber"})
        if can_view_incidents:
            kpis.extend([
                {"label": "Open Incidents", "value": open_incident_count, "icon": "fa-triangle-exclamation", "color": "rose"},
                {"label": "Critical Incidents", "value": critical_incident_count, "icon": "fa-fire", "color": "rose"},
            ])
        if can_view_sla:
            kpis.append({"label": "SLA Breaches", "value": breached_sla.count(), "icon": "fa-stopwatch", "color": "purple"})
        if can_view_housing and can_view_units:
            kpis.append({"label": "Occupied Units", "value": f"{occupied_unit_count} / {total_units}", "icon": "fa-house", "color": "emerald"})
            if can_view_occupants:
                kpis.append({"label": "Occupant Capacity", "value": f"{occupancy_rate}%", "icon": "fa-bed", "color": "emerald"})
            if can_view_incidents:
                kpis.append({"label": "Open Housing Issues", "value": houses_qs.filter(incidents__status__in=open_incident_statuses).distinct().count(), "icon": "fa-house-circle-exclamation", "color": "amber"})

        try:
            app_groups = registry.sidebar(self.app_label)
        except Exception:
            app_groups = []

        return {
            "dashboard_title": "Maintenance Command Center",
            "dashboard_subtitle": (
                str(selected_plant)
                if selected_plant
                else "All authorized plants" if not user.is_superuser
                else "All treatment plants"
            ),
            "active_tab": tab,
            "dashboard_notice": dashboard_notice,
            "invalid_plant": invalid_plant,
            "can_access_dashboard": can_access_dashboard,
            "can_view_housing": can_view_housing,
            "can_view_units": can_view_units,
            "can_view_occupants": can_view_occupants,
            "can_add_occupants": can_add_occupants,
            "can_change_occupants": can_change_occupants,
            "can_transfer_occupants": can_transfer_occupants,
            "can_view_incidents": can_view_incidents,
            "can_view_requests": can_view_requests,
            "can_view_orders": can_view_orders,
            "can_view_sla": can_view_sla,
            "can_change_houses": self._has_perm(user, DutyHouse, "change"),
            "can_change_incidents": self._has_perm(user, MaintenanceIncident, "change"),
            "can_add_incidents": can_add_incidents,
            "can_change_requests": self._has_perm(user, WorkRequest, "change"),
            "can_add_requests": self._has_perm(user, WorkRequest, "add"),
            "can_change_orders": self._has_perm(user, WorkOrder, "change"),
            "can_add_orders": self._has_perm(user, WorkOrder, "add"),
            "plant_options": all_user_plants,
            "incident_report_houses": incident_report_houses,
            "selected_plant": selected_plant,
            "plant_filter": requested_plant,
            "kpis": kpis,
            "open_requests": open_requests.order_by("-created_at")[:40],
            "work_orders": active_orders.order_by("-created_at")[:40],
            "all_orders": orders_qs.order_by("-created_at")[:100],
            "incidents": incident_rows,
            "all_incidents": incidents_qs.order_by("-reported_at")[:100],
            "incident_filter_count": incidents_base.count(),
            "incident_status_choices": IncidentStatus.choices,
            "incident_severity_choices": IncidentSeverity.choices,
            "incident_type_choices": IncidentType.choices,
            "incident_search": incident_search,
            "incident_status_filter": incident_status,
            "severity_filter": incident_severity,
            "incident_type_filter": incident_type,
            "incident_sort": incident_sort,
            "date_from": request.GET.get("date_from", ""),
            "date_to": request.GET.get("date_to", ""),
            "incident_trend": incident_trend,
            "incident_severity_bars": incident_severity_bars,
            "incident_age_bars": incident_age,
            "median_response_label": median_response_label,
            "median_resolution_label": median_resolution_label,
            "incident_status_counts": incident_status_counts,
            "duty_houses": house_rows,
            "house_filter_count": houses_base.count(),
            "house_status_choices": DutyHouse._meta.get_field("status").choices,
            "house_status_filter": house_status,
            "house_search": house_search,
            "house_location_filter": house_location,
            "location_options": location_options,
            "house_status_bars": house_status_bars,
            "location_bars": location_rows,
            "selected_house": selected_house,
            "house_detail_units": house_detail_units,
            "house_detail_occupancies": house_detail_occupancies,
            "house_detail_users": house_detail_users,
            "house_detail_current_occupancies": house_detail_current_occupancies,
            "house_checkin_units": house_checkin_units,
            "house_detail_transfer_units": house_detail_transfer_units,
            "house_detail_incidents": house_detail_incidents,
            "house_detail_orders": house_detail_orders,
            "occupancy_rate": occupancy_rate,
            "occupied_units": occupied_unit_count,
            "total_units": total_units,
            "total_capacity": total_capacity,
            "current_occupants": current_occupants,
            "over_capacity_units": over_capacity_count,
            "open_requests_count": open_requests.count(),
            "active_orders_count": active_orders.count(),
            "open_incidents_count": open_incident_count,
            "critical_incidents_count": critical_incident_count,
            "open_requests_statuses": open_request_statuses,
            "due_soon": due_soon.order_by("resolution_due")[:40],
            "breached_sla": breached_sla.order_by("resolution_due")[:40],
            "sla_records": sla_qs.order_by("resolution_due")[:100],
            "occupancy_rate_legacy": occupancy_rate,
            "occupied_units_legacy": occupied_unit_count,
            "total_units_legacy": total_units,
            "recent_activity": recent_activity,
            "app_groups": app_groups,
            "app": {"name": self.app_label, "label": "Maintenance"},
            "stats": {
                "houses": houses_qs.count(),
                "requests": requests_qs.count(),
                "orders": orders_qs.count(),
                "incidents": incidents_qs.count(),
            },
            # Retain filtered querysets for authorized CSV exports.
            "_export_incidents": incidents_base,
            "_export_houses": houses_base,
        }

    def export_csv(self, context, tab):
        import csv

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="maintenance-{tab}.csv"'
        response["Cache-Control"] = "private, no-store"
        writer = csv.writer(response)
        if tab == "incidents" and context["can_view_incidents"]:
            writer.writerow(["Incident", "Title", "Plant", "House", "Equipment", "Type", "Severity", "Status", "Reported", "Assigned to", "Impact", "Root cause", "Resolution"])
            for incident in context["_export_incidents"].select_related(
                "plant", "duty_house", "equipment", "assigned_to"
            )[:10000]:
                writer.writerow([
                    incident.incident_no,
                    incident.title,
                    incident.plant or "",
                    incident.duty_house or "",
                    incident.equipment or "",
                    incident.get_incident_type_display(),
                    incident.get_severity_display(),
                    incident.get_status_display(),
                    timezone.localtime(incident.reported_at).isoformat(),
                    incident.assigned_to or "",
                    incident.estimated_impact_score,
                    incident.root_cause,
                    incident.resolution_summary,
                ])
        elif tab == "housing" and context["can_view_housing"]:
            from maintenance.models import DutyHouseUnit

            can_view_units = context["can_view_units"]
            can_view_occupants = context["can_view_occupants"]
            can_view_incidents = context["can_view_incidents"]
            headers = ["House", "Name", "Plant", "Location", "Status", "Condition score", "Critical issues"]
            if can_view_units:
                headers.extend(["Units", "Capacity"])
            if can_view_occupants:
                headers.append("Current occupants")
            if can_view_incidents:
                headers.append("Open incidents")
            writer.writerow(headers)

            house_queryset = context["_export_houses"]
            house_ids = house_queryset.values("pk")
            capacity_by_house = (
                dict(
                    DutyHouseUnit.objects.filter(duty_house_id__in=house_ids)
                    .values("duty_house_id")
                    .annotate(total=Sum("max_occupants"))
                    .values_list("duty_house_id", "total")
                )
                if can_view_units
                else {}
            )
            annotations = {}
            if can_view_units:
                annotations["unit_count"] = Count("units", distinct=True)
            if can_view_occupants:
                annotations["occupant_count"] = Count(
                    "occupancies", filter=Q(occupancies__is_current=True), distinct=True
                )
            if can_view_incidents:
                annotations["open_incident_count"] = Count(
                    "incidents",
                    filter=Q(incidents__status__in=[
                        "reported", "under_review", "confirmed", "escalated", "auto_dispatched"
                    ]),
                    distinct=True,
                )
            houses = house_queryset.select_related("plant", "location").annotate(**annotations)
            for house in houses[:10000]:
                row = [
                    house.house_number,
                    house.name or "",
                    house.plant,
                    house.location,
                    house.get_status_display(),
                    house.maintenance_score,
                    house.critical_issues_open,
                ]
                if can_view_units:
                    row.extend([house.unit_count, capacity_by_house.get(house.pk, 0) or 0])
                if can_view_occupants:
                    row.append(house.occupant_count)
                if can_view_incidents:
                    row.append(house.open_incident_count)
                writer.writerow(row)
        else:
            writer.writerow(["No exportable records for this section"])
        return response

    def _recent_activity(self, requests_qs, orders_qs, incidents_qs):
        items = []
        for request in requests_qs.order_by("-created_at")[:6]:
            items.append({
                "kind": "request", "title": request.title,
                "meta": request.get_status_display(), "when": request.created_at,
                "tone": "cyan",
            })
        for order in orders_qs.order_by("-updated_at")[:6]:
            items.append({
                "kind": "order", "title": str(order),
                "meta": order.get_status_display(), "when": order.updated_at,
                "tone": "amber",
            })
        for incident in incidents_qs.order_by("-reported_at")[:8]:
            items.append({
                "kind": "incident", "title": incident.incident_no,
                "meta": f"{incident.get_severity_display()} · {incident.get_status_display()}",
                "when": incident.reported_at, "tone": "rose",
            })
        items.sort(key=lambda item: item["when"] or timezone.now(), reverse=True)
        return items[:15]
