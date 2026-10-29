from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from core.mixins import WanjalaMixin
from core.models import Section
from sc.models import (
    Apparatus,
    ApparatusCondition,
    AuditLog,
    MonthlyDutyRoster,
    Shift,
    ShiftAssignment,
    ShiftHandover,
    ShiftSectionRequirement,
    ShiftSupervisor,
)
from t.models import TreatmentPlant


class DashboardView(WanjalaMixin, View):
    """Operational shift dashboard built from SC domain records."""

    template_name = "sc/dashboard.html"
    app_label = "sc"

    def get(self, request):
        if response := self.process_request(request):
            return response
        self.check_idle_timeout()
        today = timezone.localdate()
        start_of_month = today.replace(day=1)
        start_of_week = today - timedelta(days=today.weekday())
        today_time = timezone.localtime().time()

        is_superuser = bool(request.user.is_superuser)
        plant_options = TreatmentPlant.objects.order_by("name") if is_superuser else TreatmentPlant.objects.filter(
            pk=getattr(request.user, "assigned_treatment_plant_id", None)
        )
        selected_plant = None
        if is_superuser:
            requested_plant = request.GET.get("plant")
            if requested_plant and requested_plant.isdigit():
                selected_plant = TreatmentPlant.objects.filter(pk=int(requested_plant)).first()
        else:
            selected_plant = getattr(request.user, "assigned_treatment_plant", None)

        shifts = Shift.objects.filter(is_deleted=False)
        if selected_plant:
            shifts = shifts.filter(treatment_plant=selected_plant)
        elif not is_superuser:
            shifts = shifts.none()
        assignments = ShiftAssignment.objects.filter(is_deleted=False, shift__in=shifts)
        handovers = ShiftHandover.objects.filter(shift__in=shifts)
        requirements = ShiftSectionRequirement.objects.filter(shift__in=shifts).select_related(
            "shift", "section"
        ).order_by("shift__start_time", "section__name")
        supervisors = ShiftSupervisor.objects.filter(is_active=True)
        apparatus = Apparatus.objects.select_related("equipment", "equipment__section")
        if selected_plant:
            supervisors = supervisors.filter(treatment_plant=selected_plant)
            apparatus = apparatus.filter(equipment__section__treatment_plant=selected_plant)
        elif not is_superuser:
            supervisors = supervisors.none()
            apparatus = apparatus.none()

        shift_rows = list(shifts.select_related("treatment_plant").order_by("start_time", "name"))
        current_shifts = []
        for shift in shift_rows:
            on_duty = (
                shift.start_time <= today_time < shift.end_time
                if not shift.is_overnight
                else today_time >= shift.start_time or today_time < shift.end_time
            )
            shift.is_active_now = on_duty
            if on_duty:
                current_shifts.append(shift)

        today_assignments = assignments.filter(date=today)
        today_assignment_rows = today_assignments.select_related(
            "staff", "staff__section", "shift"
        ).order_by("shift__start_time", "staff__last_name", "staff__first_name")[:30]
        roster_day_type = today_assignments.values_list("day_type", flat=True).first()
        if roster_day_type not in {choice for choice, _label in ShiftAssignment.DAYTYPE_CHOICES}:
            roster_day_type = (
                ShiftAssignment.DAYTYPE_WEEKEND if today.weekday() >= 5 else ShiftAssignment.DAYTYPE_WEEKDAY
            )
        today_attendance = {
            row["attendance_status"]: row["count"]
            for row in today_assignments.values("attendance_status").annotate(count=Count("pk"))
        }
        month_attendance = {
            row["attendance_status"]: row["count"]
            for row in assignments.filter(date__gte=start_of_month, date__lte=today)
            .values("attendance_status").annotate(count=Count("pk"))
        }
        monthly_total = sum(month_attendance.values())
        present_month = month_attendance.get(ShiftAssignment.ATTENDANCE_PRESENT, 0)
        attendance_rate = round(present_month * 100 / monthly_total) if monthly_total else 0

        today_by_slot = {
            (row["shift_id"], row["staff__section_id"]): row["count"]
            for row in today_assignments.values("shift_id", "staff__section_id").annotate(count=Count("pk"))
        }
        coverage_rows = []
        required_total = assigned_total = understaffed_count = 0
        for requirement in requirements:
            required = requirement.get_required_staff(roster_day_type)
            assigned = today_by_slot.get((requirement.shift_id, requirement.section_id), 0)
            fill = round(min(assigned, required) * 100 / required) if required else 100
            gap = max(0, required - assigned)
            required_total += required
            assigned_total += min(assigned, required)
            understaffed_count += int(gap > 0)
            coverage_rows.append({
                "shift": requirement.shift.name,
                "section": requirement.section.name,
                "assigned": assigned,
                "required": required,
                "gap": gap,
                "fill": fill,
            })
        coverage_rate = round(assigned_total * 100 / required_total) if required_total else 0

        week_assignments = assignments.filter(date__gte=start_of_week, date__lte=start_of_week + timedelta(days=6))
        planned_by_day = {
            row["date"]: row["total"]
            for row in week_assignments.values("date").annotate(total=Count("pk"))
        }
        present_by_day = {
            row["date"]: row["present"]
            for row in week_assignments.filter(date__lte=today).values("date").annotate(
                present=Count("pk", filter=Q(attendance_status=ShiftAssignment.ATTENDANCE_PRESENT))
            )
        }
        trend = []
        for offset in range(7):
            day = start_of_week + timedelta(days=offset)
            trend.append({
                "label": day.strftime("%a"),
                "date": day.isoformat(),
                "total": planned_by_day.get(day, 0),
                "present": present_by_day.get(day, 0),
            })

        latest_handover_ids = list(handovers.order_by("-date", "-handed_over_at").values_list("pk", flat=True)[:10])
        latest_handovers = handovers.filter(pk__in=latest_handover_ids).select_related(
            "shift", "outgoing_supervisor", "incoming_supervisor"
        ).order_by("-date", "-handed_over_at")

        latest_conditions = ApparatusCondition.objects.filter(
            apparatus__in=apparatus
        ).select_related("apparatus", "handover")
        latest_by_apparatus = {}
        for condition in latest_conditions.order_by("apparatus_id", "-handover__date", "-handover__handed_over_at"):
            latest_by_apparatus.setdefault(condition.apparatus_id, condition)
        apparatus_list = list(apparatus.order_by("name"))
        apparatus_rows = []
        for item in apparatus_list:
            condition = latest_by_apparatus.get(item.pk)
            apparatus_rows.append({
                "name": item.name,
                "equipment": item.equipment.name,
                "status": condition.status if condition else "unreported",
                "remarks": condition.remarks if condition else "No condition recorded yet",
                "date": condition.handover.date if condition else None,
            })
        apparatus_attention = sum(
            (latest_by_apparatus.get(item.pk).status if latest_by_apparatus.get(item.pk) else "unreported")
            in {"needs_repair", "out_of_service", "unreported"}
            for item in apparatus_list
        )
        apparatus_rows = apparatus_rows[:15]

        sections = Section.objects.order_by("name")
        if selected_plant:
            sections = sections.filter(treatment_plant=selected_plant)
        elif not is_superuser:
            sections = sections.none()
        section_count = sections.count()
        month_rosters = MonthlyDutyRoster.objects.filter(month=today.month, year=today.year)
        if selected_plant:
            month_rosters = month_rosters.filter(treatment_plant=selected_plant)
        elif not is_superuser:
            month_rosters = month_rosters.none()
        roster_count = month_rosters.count()
        roster_rows = month_rosters.select_related("treatment_plant", "created_by").annotate(
            assignment_count=Count("assignments", filter=Q(assignments__is_deleted=False))
        ).order_by(
            "treatment_plant__name", "month", "year"
        )[:12]

        audit_logs = AuditLog.objects.select_related("user", "content_type").order_by("-timestamp")
        if not is_superuser:
            audit_logs = audit_logs.filter(user=request.user)
        audit_logs = audit_logs[:10]

        nav_items = [
            {"id": "overview", "label": "Operations overview", "icon": "gauge-high"},
            {"id": "shift-catalog", "label": "Shift catalogue", "icon": "arrows-rotate"},
            {"id": "staffing", "label": "Staffing coverage", "icon": "people-group"},
            {"id": "attendance", "label": "Attendance", "icon": "user-check"},
            {"id": "rosters", "label": "Monthly duty rosters", "icon": "calendar-days"},
            {"id": "supervisors", "label": "Shift supervisors", "icon": "user-shield"},
            {"id": "handovers", "label": "Shift handovers", "icon": "right-left"},
            {"id": "apparatus", "label": "Apparatus condition", "icon": "screwdriver-wrench"},
            {"id": "activity", "label": "Audit activity", "icon": "clock-rotate-left"},
        ]
        return render(request, self.template_name, {
            "app": {"name": "Shift Control", "label": "Shift Control"},
            "plant_options": plant_options,
            "selected_plant": selected_plant,
            "show_plant_selector": is_superuser,
            "selected_section": request.GET.get("section", "overview"),
            "today": today,
            "month_label": today.strftime("%B %Y"),
            "roster_count": roster_count,
            "nav_items": nav_items,
            "kpis": [
                {"label": "Active shifts", "value": len(shift_rows), "detail": f"{len(current_shifts)} running now", "icon": "arrows-spin", "tone": "cyan", "target": "overview"},
                {"label": "Today's roster", "value": today_assignments.count(), "detail": f"{today_attendance.get('present', 0)} marked present", "icon": "clipboard-list", "tone": "blue", "target": "attendance"},
                {"label": "Staffing coverage", "value": f"{coverage_rate}%", "detail": f"{understaffed_count} shift-section gaps", "icon": "people-group", "tone": "amber", "target": "staffing"},
                {"label": "Attendance this month", "value": f"{attendance_rate}%", "detail": f"{monthly_total:,} recorded assignments", "icon": "user-check", "tone": "green", "target": "attendance"},
                {"label": "Handover waiting", "value": handovers.filter(is_taken_over=False).count(), "detail": "Awaiting takeover", "icon": "right-left", "tone": "rose", "target": "handovers"},
                {"label": "Active supervisors", "value": supervisors.count(), "detail": f"Across {section_count} operational sections", "icon": "user-shield", "tone": "violet", "target": "supervisors"},
                {"label": "Apparatus attention", "value": apparatus_attention, "detail": "Repair, out of service or unreported", "icon": "screwdriver-wrench", "tone": "rose", "target": "apparatus"},
                {"label": "Rosters this month", "value": roster_count, "detail": "Monthly duty plans", "icon": "calendar-days", "tone": "blue", "target": "rosters"},
            ],
            "current_shifts": current_shifts,
            "shift_rows": shift_rows,
            "today_assignment_rows": today_assignment_rows,
            "shift_count": len(shift_rows),
            "coverage_rows": coverage_rows,
            "coverage_rate": coverage_rate,
            "understaffed_count": understaffed_count,
            "attendance_today": today_attendance,
            "attendance_month": month_attendance,
            "attendance_trend": trend,
            "coverage_chart": {
                "labels": [row["shift"] + " · " + row["section"] for row in coverage_rows[:10]],
                "values": [row["fill"] for row in coverage_rows[:10]],
            },
            "latest_handovers": latest_handovers,
            "roster_rows": roster_rows,
            "apparatus_rows": apparatus_rows,
            "apparatus_attention": apparatus_attention,
            "supervisors": supervisors.select_related("user", "section", "treatment_plant").order_by(
                "section__name", "user__last_name", "user__first_name"
            )[:20],
            "audit_logs": audit_logs,
        })
