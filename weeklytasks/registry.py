
from __future__ import annotations

import logging
import re
from typing import Any

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "weeklytasks"


def get_model(name: str):
    model = apps.get_model(APP_LABEL, name)

    if model is None:
        raise RuntimeError(
            f"Unable to resolve model '{APP_LABEL}.{name}'."
        )

    return model


StandardWeeklyTask = get_model("StandardWeeklyTask")
MonthlyDutySchedule = get_model("MonthlyDutySchedule")
DutyWeek = get_model("DutyWeek")
WeeklyDutyTask = get_model("WeeklyDutyTask")
DailyTaskAssignment = get_model("DailyTaskAssignment")
DutyConfirmation = get_model("DutyConfirmation")


ICONS = {
    "StandardWeeklyTask": "clipboard-list",
    "MonthlyDutySchedule": "calendar-alt",
    "DutyWeek": "calendar-week",
    "WeeklyDutyTask": "tasks",
    "DailyTaskAssignment": "user-check",
    "DutyConfirmation": "check-circle",
}


GROUPS = {
    "StandardWeeklyTask": "task_catalog",
    "MonthlyDutySchedule": "scheduling",
    "DutyWeek": "scheduling",
    "WeeklyDutyTask": "task_assignment",
    "DailyTaskAssignment": "task_execution",
    "DutyConfirmation": "task_execution",
}


def humanize_model_name(model) -> str:
    verbose_name = getattr(model._meta, "verbose_name", None)

    if verbose_name:
        return str(verbose_name).strip().title()

    return re.sub(
        r"(?<!^)(?=[A-Z])",
        " ",
        model.__name__,
    ).strip()


def humanize_plural_name(model, singular: str) -> str:
    verbose_name_plural = getattr(
        model._meta,
        "verbose_name_plural",
        None,
    )

    if verbose_name_plural:
        return str(verbose_name_plural).strip().title()

    if singular.endswith(("s", "x", "z", "ch", "sh")):
        return f"{singular}es"

    return f"{singular}s"


def build_meta(model) -> dict[str, Any]:
    verbose_name = humanize_model_name(model)

    return {
        "key": (
            f"{model._meta.app_label}."
            f"{model._meta.model_name}"
        ),
        "app_label": model._meta.app_label,
        "model_name": model._meta.model_name,
        "verbose_name": verbose_name,
        "verbose_name_plural": humanize_plural_name(
            model,
            verbose_name,
        ),
    }


def standard_task_qs(model) -> QuerySet:
    return model.objects.all()


def monthly_schedule_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "created_by",
    )


def duty_week_qs(model) -> QuerySet:
    return model.objects.select_related(
        "schedule",
        "schedule__treatment_plant",
    )


def weekly_task_qs(model) -> QuerySet:
    return (
        model.objects.select_related(
            "week",
            "week__schedule",
            "treatment_plant",
            "task_template",
        )
        .prefetch_related(
            "daily_assignments",
        )
    )


def daily_assignment_qs(model) -> QuerySet:
    return model.objects.select_related(
        "task",
        "task__week",
        "task__task_template",
        "user",
        "user__section",
        "shift",
    )


def duty_confirmation_qs(model) -> QuerySet:
    return model.objects.select_related(
        "assignment",
        "assignment__task",
        "assignment__user",
        "confirmed_by",
    )


def safe_register(model, **kwargs):
    if model is None:
        raise RuntimeError(
            "Cannot register an unresolved weeklytasks model."
        )

    model_name = model.__name__

    meta = dict(kwargs.pop("meta", {}) or {})
    meta.update(build_meta(model))
    kwargs["meta"] = meta

    ui = dict(kwargs.pop("ui", {}) or {})
    ui.setdefault(
        "icon",
        ICONS.get(model_name, "tasks"),
    )
    ui.setdefault(
        "group",
        GROUPS.get(model_name, "general"),
    )
    kwargs["ui"] = ui

    kwargs.pop("templates", None)

    try:
        registered = register_model(**kwargs)(model)

        logger.debug(
            "[weeklytasks.registry] registered %s.%s",
            model._meta.app_label,
            model._meta.model_name,
        )

        return registered

    except Exception:
        logger.exception(
            "[weeklytasks.registry] failed registering %s.%s",
            model._meta.app_label,
            model._meta.model_name,
        )
        raise


safe_register(
    StandardWeeklyTask,
    search_fields=[
        "code",
        "name",
    ],
    filter_fields=[
        "is_active",
    ],
    ordering=[
        "code",
        "name",
    ],
    inline_edit_fields=[
        "code",
        "name",
        "is_active",
    ],
    queryset_factory=standard_task_qs,
)


safe_register(
    MonthlyDutySchedule,
    search_fields=[
        "treatment_plant__name",
        "notes",
    ],
    filter_fields=[
        "month",
        "year",
        "treatment_plant",
    ],
    ordering=[
        "-year",
        "-month",
    ],
    select_related=[
        "treatment_plant",
        "created_by",
    ],
    inline_edit_fields=[
        "month",
        "year",
        "notes",
    ],
    queryset_factory=monthly_schedule_qs,
)


safe_register(
    DutyWeek,
    search_fields=[
        "schedule__treatment_plant__name",
    ],
    filter_fields=[
        "schedule",
    ],
    ordering=[
        "start_date",
        "end_date",
    ],
    select_related=[
        "schedule",
        "schedule__treatment_plant",
    ],
    inline_edit_fields=[
        "start_date",
        "end_date",
    ],
    queryset_factory=duty_week_qs,
)


safe_register(
    WeeklyDutyTask,
    search_fields=[
        "task_template__name",
        "treatment_plant__name",
    ],
    filter_fields=[
        "week",
        "treatment_plant",
        "task_template",
    ],
    ordering=[
        "week",
        "task_template",
    ],
    select_related=[
        "week",
        "week__schedule",
        "treatment_plant",
        "task_template",
    ],
    inline_edit_fields=[
        "treatment_plant",
    ],
    queryset_factory=weekly_task_qs,
)


safe_register(
    DailyTaskAssignment,
    search_fields=[
        "user__username",
        "task__task_template__name",
    ],
    filter_fields=[
        "task",
        "user",
        "date",
        "shift",
    ],
    ordering=[
        "-date",
        "shift",
        "user",
    ],
    select_related=[
        "task",
        "task__week",
        "task__task_template",
        "user",
        "user__section",
        "shift",
    ],
    queryset_factory=daily_assignment_qs,
    inline_edit_fields=[
        "date",
        "shift",
        "remarks",
    ],
)


safe_register(
    DutyConfirmation,
    search_fields=[
        "assignment__task__task_template__name",
        "confirmed_by__username",
    ],
    filter_fields=[
        "assignment",
        "confirmed_by",
    ],
    ordering=[
        "-confirmed_at",
    ],
    select_related=[
        "assignment",
        "assignment__task",
        "assignment__user",
        "confirmed_by",
    ],
    inline_edit_fields=[
        "confirmed_at",
        "notes",
    ],
)


try:
    from core.registry import registry

    logger.info(
        "[weeklytasks.registry] loaded app=%s registry_models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[weeklytasks.registry] registry unavailable during import"
    )

