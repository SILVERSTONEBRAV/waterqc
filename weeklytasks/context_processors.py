from __future__ import annotations

from django.utils import timezone

from .models import DailyTaskAssignment, WeeklyDutyTask


WATER_TREATMENT_CHEMICAL_ANALYSIS = "Water Treatment Chemical Analysis"


def water_treatment_chemical_analysis_context(request):
    context = {
        "water_treatment_chemical_analysis": None,
        "water_treatment_chemical_analysis_task": None,
        "water_treatment_chemical_analysis_analysts": [],
    }

    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return context

    treatment_plant_id = getattr(
        user,
        "assigned_treatment_plant_id",
        None,
    )
    section_id = getattr(
        user,
        "section_id",
        None,
    )

    if not treatment_plant_id or not section_id:
        return context

    now = timezone.localtime()
    current_date = now.date()
    current_time = now.time()

    task = (
        WeeklyDutyTask.objects
        .select_related(
            "week",
            "week__schedule",
            "task_template",
            "treatment_plant",
            "section",
        )
        .filter(
            task_template__name__iexact=WATER_TREATMENT_CHEMICAL_ANALYSIS,
            task_template__is_active=True,
            treatment_plant_id=treatment_plant_id,
            section_id=section_id,
            week__start_date__lte=current_date,
            week__end_date__gte=current_date,
        )
        .order_by(
            "-week__start_date",
            "-created_at",
        )
        .first()
    )

    if not task:
        return context

    assignments = (
        DailyTaskAssignment.objects
        .select_related(
            "user",
            "user__section",
            "user__assigned_treatment_plant",
            "shift",
        )
        .filter(
            task=task,
            date=current_date,
            user__is_active=True,
            user__assigned_treatment_plant_id=treatment_plant_id,
            user__section_id=section_id,
            shift__is_deleted=False,
        )
        .order_by(
            "user__last_name",
            "user__first_name",
            "user__username",
        )
    )

    analysts = []

    for assignment in assignments:
        shift = assignment.shift

        if not shift:
            continue

        if shift.start_time <= current_time < shift.end_time:
            analysts.append(assignment.user)

    context["water_treatment_chemical_analysis"] = {
        "task": task,
        "analysts": analysts,
        "analyst_count": len(analysts),
        "active": bool(analysts),
    }

    context["water_treatment_chemical_analysis_task"] = task
    context["water_treatment_chemical_analysis_analysts"] = analysts

    return context
