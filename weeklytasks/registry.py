from __future__ import annotations

import logging
import re
from typing import Any

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Model, QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "weeklytasks"

MODEL_NAMES = (
    "StandardWeeklyTask",
    "MonthlyDutySchedule",
    "DutyWeek",
    "WeeklyDutyTask",
    "DailyTaskAssignment",
)

ICONS = {
    "StandardWeeklyTask": "clipboard-list",
    "MonthlyDutySchedule": "calendar-alt",
    "DutyWeek": "calendar-week",
    "WeeklyDutyTask": "tasks",
    "DailyTaskAssignment": "user-check",
}

GROUPS = {
    "StandardWeeklyTask": "task_catalog",
    "MonthlyDutySchedule": "scheduling",
    "DutyWeek": "scheduling",
    "WeeklyDutyTask": "task_assignment",
    "DailyTaskAssignment": "task_execution",
}

MODEL_CONFIG: dict[str, dict[str, Any]] = {
    "StandardWeeklyTask": {
        "search_fields": ("code", "name", "description"),
        "filter_fields": ("is_active",),
        "ordering": ("code", "name"),
        "inline_edit_fields": ("code", "name", "description", "is_active"),
        "queryset_factory": "standard_task_qs",
    },
    "MonthlyDutySchedule": {
        "search_fields": (
            "treatment_plant__name",
            "section__name",
            "notes",
        ),
        "filter_fields": (
            "month",
            "year",
            "treatment_plant",
            "section",
        ),
        "ordering": ("-year", "-month", "treatment_plant", "section"),
        "inline_edit_fields": ("month", "year", "notes"),
        "select_related": ("treatment_plant", "section", "created_by"),
        "queryset_factory": "monthly_schedule_qs",
    },
    "DutyWeek": {
        "search_fields": (
            "schedule__treatment_plant__name",
            "schedule__section__name",
        ),
        "filter_fields": ("schedule", "start_date", "end_date"),
        "ordering": ("start_date", "end_date"),
        "inline_edit_fields": ("start_date", "end_date"),
        "select_related": ("schedule", "schedule__treatment_plant", "schedule__section"),
        "queryset_factory": "duty_week_qs",
    },
    "WeeklyDutyTask": {
        "search_fields": (
            "task_template__code",
            "task_template__name",
            "treatment_plant__name",
            "section__name",
        ),
        "filter_fields": (
            "week",
            "treatment_plant",
            "section",
            "task_template",
        ),
        "ordering": ("week__start_date", "task_template__code"),
        "inline_edit_fields": ("treatment_plant", "section", "task_template"),
        "select_related": (
            "week",
            "week__schedule",
            "week__schedule__treatment_plant",
            "week__schedule__section",
            "treatment_plant",
            "section",
            "task_template",
        ),
        "prefetch_related": ("daily_assignments",),
        "queryset_factory": "weekly_task_qs",
    },
    "DailyTaskAssignment": {
        "search_fields": (
            "user__username",
            "user__first_name",
            "user__last_name",
            "task__task_template__code",
            "task__task_template__name",
            "task__section__name",
        ),
        "filter_fields": ("task", "user", "date", "shift"),
        "ordering": ("-date", "shift__start_time", "user__last_name"),
        "inline_edit_fields": ("date", "shift", "remarks"),
        "select_related": (
            "task",
            "task__week",
            "task__task_template",
            "task__section",
            "task__treatment_plant",
            "user",
            "user__section",
            "shift",
        ),
        "queryset_factory": "daily_assignment_qs",
    },
}


def get_model(name: str) -> type[Model]:
    try:
        model = apps.get_model(APP_LABEL, name)
    except LookupError as exc:
        raise RuntimeError(
            f"Unable to resolve model '{APP_LABEL}.{name}'. "
            "Check INSTALLED_APPS and the model class name."
        ) from exc

    if model is None:
        raise RuntimeError(
            f"Unable to resolve model '{APP_LABEL}.{name}'."
        )

    return model


def humanize_model_name(model: type[Model]) -> str:
    verbose_name = getattr(model._meta, "verbose_name", None)

    if verbose_name:
        return str(verbose_name).strip().title()

    return re.sub(
        r"(?<!^)(?=[A-Z])",
        " ",
        model.__name__,
    ).strip()


def humanize_plural_name(
    model: type[Model],
    singular: str,
) -> str:
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


def build_meta(model: type[Model]) -> dict[str, Any]:
    singular = humanize_model_name(model)

    return {
        "key": f"{model._meta.app_label}.{model._meta.model_name}",
        "app_label": model._meta.app_label,
        "model_name": model._meta.model_name,
        "verbose_name": singular,
        "verbose_name_plural": humanize_plural_name(model, singular),
    }


def get_field_path(
    model: type[Model],
    path: str,
    *,
    require_relation: bool = False,
) -> bool:
    current_model = model
    parts = path.split("__")

    for index, part in enumerate(parts):
        try:
            field = current_model._meta.get_field(part)
        except FieldDoesNotExist:
            return False

        is_last = index == len(parts) - 1

        if not is_last:
            related_model = getattr(field, "related_model", None)

            if related_model is None:
                return False

            current_model = related_model
        elif require_relation and not field.is_relation:
            return False

    return True


def valid_field_paths(
    model: type[Model],
    paths: tuple[str, ...] | list[str],
    *,
    require_relation: bool = False,
    setting_name: str,
) -> list[str]:
    valid: list[str] = []

    for path in paths:
        if get_field_path(
            model,
            path,
            require_relation=require_relation,
        ):
            valid.append(path)
        else:
            logger.warning(
                "[weeklytasks.registry] ignoring invalid %s=%r for %s.%s",
                setting_name,
                path,
                model._meta.app_label,
                model._meta.model_name,
            )

    return valid


def standard_task_qs(model: type[Model]) -> QuerySet:
    return model.objects.all()


def monthly_schedule_qs(model: type[Model]) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
        "section",
        "created_by",
    )


def duty_week_qs(model: type[Model]) -> QuerySet:
    return model.objects.select_related(
        "schedule",
        "schedule__treatment_plant",
        "schedule__section",
    )


def weekly_task_qs(model: type[Model]) -> QuerySet:
    return (
        model.objects.select_related(
            "week",
            "week__schedule",
            "week__schedule__treatment_plant",
            "week__schedule__section",
            "treatment_plant",
            "section",
            "task_template",
        )
        .prefetch_related("daily_assignments")
    )


def daily_assignment_qs(model: type[Model]) -> QuerySet:
    return model.objects.select_related(
        "task",
        "task__week",
        "task__task_template",
        "task__section",
        "task__treatment_plant",
        "user",
        "user__section",
        "shift",
    )


QUERYSET_FACTORIES = {
    "standard_task_qs": standard_task_qs,
    "monthly_schedule_qs": monthly_schedule_qs,
    "duty_week_qs": duty_week_qs,
    "weekly_task_qs": weekly_task_qs,
    "daily_assignment_qs": daily_assignment_qs,
}


def build_registration_config(
    model: type[Model],
    config: dict[str, Any],
) -> dict[str, Any]:
    registration: dict[str, Any] = {}

    for key in ("search_fields", "filter_fields", "ordering", "inline_edit_fields"):
        configured = config.get(key, ())

        if key == "ordering":
            valid: list[str] = []

            for expression in configured:
                descending = expression.startswith("-")
                field_path = expression[1:] if descending else expression

                if get_field_path(model, field_path):
                    valid.append(expression)
                else:
                    logger.warning(
                        "[weeklytasks.registry] ignoring invalid ordering=%r for %s",
                        expression,
                        model.__name__,
                    )

            registration[key] = valid
            continue

        valid_paths = valid_field_paths(
            model,
            configured,
            setting_name=key,
        )

        if key == "inline_edit_fields":
            concrete_fields = {
                field.name
                for field in model._meta.concrete_fields
                if not field.primary_key
                and not field.auto_created
                and not field.many_to_many
            }
            valid_paths = [
                field_name
                for field_name in valid_paths
                if "__" not in field_name
                and field_name in concrete_fields
                and not model._meta.get_field(field_name).auto_created
            ]

        registration[key] = valid_paths

    configured_select_related = config.get("select_related", ())
    registration["select_related"] = valid_field_paths(
        model,
        configured_select_related,
        require_relation=True,
        setting_name="select_related",
    )

    configured_prefetch_related = config.get("prefetch_related", ())
    registration["prefetch_related"] = valid_field_paths(
        model,
        configured_prefetch_related,
        require_relation=True,
        setting_name="prefetch_related",
    )

    factory_name = config.get("queryset_factory")
    factory = QUERYSET_FACTORIES.get(factory_name)

    if factory is not None:
        registration["queryset_factory"] = factory
    else:
        registration["queryset_factory"] = lambda registered_model: (
            registered_model.objects.all()
        )

    return registration


def safe_register(
    model: type[Model],
    **kwargs: Any,
) -> Any:
    if model is None:
        raise RuntimeError(
            "Cannot register an unresolved weeklytasks model."
        )

    meta = dict(kwargs.pop("meta", {}) or {})
    meta.update(build_meta(model))
    kwargs["meta"] = meta

    ui = dict(kwargs.pop("ui", {}) or {})
    ui.setdefault("icon", ICONS.get(model.__name__, "clipboard-list"))
    ui.setdefault("group", GROUPS.get(model.__name__, "general"))
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


def register_weeklytasks_models() -> list[type[Model]]:
    registered_models: list[type[Model]] = []

    for model_name in MODEL_NAMES:
        model = get_model(model_name)
        config = MODEL_CONFIG.get(model_name, {})
        registration = build_registration_config(model, config)

        safe_register(
            model,
            **registration,
        )
        registered_models.append(model)

    logger.info(
        "[weeklytasks.registry] registered %s models for app=%s",
        len(registered_models),
        APP_LABEL,
    )

    return registered_models


REGISTERED_MODELS = register_weeklytasks_models()


try:
    from core.registry import registry

    logger.info(
        "[weeklytasks.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(REGISTERED_MODELS),
    )

except Exception:
    logger.exception(
        "[weeklytasks.registry] unable to inspect core registry during import"
    )
