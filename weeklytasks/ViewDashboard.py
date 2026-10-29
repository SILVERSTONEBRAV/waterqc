from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from core.mixins import WanjalaMixin
from core.models import Section
from t.models import TreatmentPlant
from .models import (
    DailyTaskAssignment,
    DutyWeek,
    MonthlyDutySchedule,
    StandardWeeklyTask,
    WeeklyDutyTask,
)


class DashboardView(WanjalaMixin, View):
    """Weekly task planning and assignment coverage from weeklytasks models."""

    template_name = "weeklytasks/dashboard.html"
    app_label = "weeklytasks"

    def get(self, request):
        if response := self.process_request(request):
            return response
        self.check_idle_timeout()
        today = timezone.localdate()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        horizon_end = today + timedelta(days=30)
        assignment_horizon_end = today + timedelta(days=14)
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

        schedules = MonthlyDutySchedule.objects.select_related("treatment_plant", "section", "created_by")
        weekly_tasks = WeeklyDutyTask.objects.select_related(
            "week", "week__schedule", "task_template", "section", "treatment_plant"
        )
        assignments = DailyTaskAssignment.objects.select_related(
            "task", "task__task_template", "user", "user__section", "shift"
        )
        templates = StandardWeeklyTask.objects.filter(is_active=True)
        if selected_plant:
            schedules = schedules.filter(treatment_plant=selected_plant)
            weekly_tasks = weekly_tasks.filter(treatment_plant=selected_plant)
            assignments = assignments.filter(task__treatment_plant=selected_plant)
        elif not is_superuser:
            schedules = schedules.none()
            weekly_tasks = weekly_tasks.none()
            assignments = assignments.none()

        current_week_tasks = weekly_tasks.filter(week__start_date__lte=end_of_week, week__end_date__gte=start_of_week)
        horizon_tasks = weekly_tasks.filter(week__start_date__lte=horizon_end, week__end_date__gte=today)
        today_assignments = assignments.filter(date=today)
        next_14d_assignments = assignments.filter(date__gte=today, date__lte=assignment_horizon_end)
        month_schedules = schedules.filter(month=today.month, year=today.year)

        horizon_assignments = assignments.filter(date__gte=today, date__lte=horizon_end, task__in=horizon_tasks)
        unstaffed_qs = horizon_tasks.annotate(
            assignment_count=Count(
                "daily_assignments",
                filter=Q(daily_assignments__date__gte=today, daily_assignments__date__lte=horizon_end),
            )
        ).filter(assignment_count=0)
        unstaffed_count = unstaffed_qs.count()
        unstaffed_tasks = list(
            unstaffed_qs.order_by("week__start_date", "section__name", "task_template__name")[:15]
        )

        no_shift_count = next_14d_assignments.filter(shift__isnull=True).count()
        shift_distribution_rows = (
            next_14d_assignments.values("shift__name")
            .annotate(count=Count("pk"))
            .order_by("shift__name")
        )
        shift_labels = [row["shift__name"] or "Shift not set" for row in shift_distribution_rows]
        shift_values = [row["count"] for row in shift_distribution_rows]

        assignment_by_day = {
            row["date"]: row["count"]
            for row in assignments.filter(date__gte=start_of_week, date__lte=end_of_week)
            .values("date").annotate(count=Count("pk"))
        }
        trend = []
        for offset in range(7):
            day = start_of_week + timedelta(days=offset)
            trend.append({
                "label": day.strftime("%a"),
                "date": day.isoformat(),
                "count": assignment_by_day.get(day, 0),
            })

        section_task_counts = {
            row["section_id"]: row
            for row in horizon_tasks.values("section_id", "section__name").annotate(
                tasks=Count("pk", distinct=True),
                staffed=Count("pk", filter=Q(daily_assignments__date__gte=today, daily_assignments__date__lte=horizon_end), distinct=True),
            )
        }
        section_assignment_counts = {
            row["task__section_id"]: row["count"]
            for row in horizon_assignments
            .values("task__section_id").annotate(count=Count("pk"))
        }
        section_rows = []
        for section_id, row in section_task_counts.items():
            task_count = row["tasks"]
            people = section_assignment_counts.get(section_id, 0)
            section_rows.append({
                "name": row["section__name"],
                "tasks": task_count,
                "assignments": people,
                "tasks_with_assignees": row["staffed"],
                "coverage": round(row["staffed"] * 100 / task_count) if task_count else 0,
            })
        section_rows.sort(key=lambda row: row["name"] or "")

        recent_schedules = schedules.order_by("-year", "-month", "section__name")[:12]
        weeks = DutyWeek.objects.filter(
            schedule__in=schedules,
            start_date__lte=horizon_end,
            end_date__gte=start_of_week,
        ).select_related("schedule", "schedule__section", "schedule__treatment_plant").annotate(
            task_count=Count("weekly_tasks", distinct=True),
            daily_assignment_count=Count("weekly_tasks__daily_assignments", distinct=True),
        ).order_by("start_date")[:20]
        current_tasks = current_week_tasks.annotate(assignment_count=Count("daily_assignments")).order_by(
            "week__start_date", "section__name", "task_template__name"
        )[:20]
        missing_shift_assignments = next_14d_assignments.filter(shift__isnull=True).order_by(
            "date", "user__last_name", "user__first_name"
        )[:15]
        daily_assignment_rows = next_14d_assignments.order_by(
            "date", "shift__start_time", "user__last_name", "user__first_name"
        )[:30]

        sections = Section.objects.order_by("name")
        if selected_plant:
            sections = sections.filter(treatment_plant=selected_plant)
        elif not is_superuser:
            sections = sections.none()

        nav_items = [
            {"id": "overview", "label": "Weekly operations", "icon": "gauge-high"},
            {"id": "schedules", "label": "Monthly schedules", "icon": "calendar-days"},
            {"id": "weeks", "label": "Duty weeks", "icon": "calendar-week"},
            {"id": "weekly-plans", "label": "Weekly duty tasks", "icon": "list-check"},
            {"id": "daily-assignments", "label": "Daily assignments", "icon": "user-clock"},
            {"id": "section-load", "label": "Section workload", "icon": "layer-group"},
            {"id": "shift-load", "label": "Shift distribution", "icon": "clock"},
            {"id": "task-library", "label": "Task library", "icon": "book-open"},
        ]

        total_horizon_tasks = horizon_tasks.count()
        staffed_horizon_tasks = max(0, total_horizon_tasks - unstaffed_count)
        return render(request, self.template_name, {
            "app": {"name": "Weekly Tasks", "label": "Weekly Tasks"},
            "plant_options": plant_options,
            "selected_plant": selected_plant,
            "show_plant_selector": is_superuser,
            "selected_section": request.GET.get("section", "overview"),
            "today": today,
            "week_label": f"{start_of_week:%d %b} – {end_of_week:%d %b %Y}",
            "nav_items": nav_items,
            "kpis": [
                {"label": "Active task templates", "value": templates.count(), "detail": "Available for weekly planning", "icon": "book-open", "tone": "cyan", "target": "task-library"},
                {"label": "Schedules this month", "value": month_schedules.count(), "detail": today.strftime("%B %Y"), "icon": "calendar-days", "tone": "blue", "target": "schedules"},
                {"label": "Tasks this week", "value": current_week_tasks.count(), "detail": week_label_text(start_of_week, end_of_week), "icon": "list-check", "tone": "violet", "target": "weekly-plans"},
                {"label": "Assignments today", "value": today_assignments.count(), "detail": f"{today_assignments.values('user_id').distinct().count()} people scheduled", "icon": "user-clock", "tone": "green", "target": "daily-assignments"},
                {"label": "Tasks without assignees", "value": unstaffed_count, "detail": "In the next 30 day plan window", "icon": "user-slash", "tone": "amber", "target": "weekly-plans"},
                {"label": "Shifts not set", "value": no_shift_count, "detail": "Assignments in the next 14 days", "icon": "clock", "tone": "rose", "target": "shift-load"},
                {"label": "Planned tasks staffed", "value": f"{round(staffed_horizon_tasks * 100 / total_horizon_tasks) if total_horizon_tasks else 0}%", "detail": f"{staffed_horizon_tasks} of {total_horizon_tasks} tasks have assignments", "icon": "chart-pie", "tone": "cyan", "target": "section-load"},
            ],
            "recent_schedules": recent_schedules,
            "weeks": weeks,
            "current_tasks": current_tasks,
            "unstaffed_tasks": unstaffed_tasks,
            "missing_shift_assignments": missing_shift_assignments,
            "daily_assignment_rows": daily_assignment_rows,
            "section_rows": section_rows,
            "trend": trend,
            "shift_chart": {"labels": shift_labels, "values": shift_values},
            "week_start": start_of_week,
            "week_end": end_of_week,
            "horizon_end": horizon_end,
            "template_rows": templates.order_by("code", "name")[:20],
            "weekly_task_count": total_horizon_tasks,
            "daily_assignment_count": assignments.filter(date__gte=today, date__lte=horizon_end).count(),
            "section_count": sections.count(),
        })


def week_label_text(start, end):
    return f"{start:%d %b} – {end:%d %b %Y}"
