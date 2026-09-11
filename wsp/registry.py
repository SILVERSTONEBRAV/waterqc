import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "wsp"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================
def get_model(name: str):
    """
    Lazy model resolver.
    Prevents circular imports during app loading.
    """
    return apps.get_model(APP_LABEL, name)


# ==========================================================
# MODEL REFERENCES
# ==========================================================
Category = get_model("Category")
ThematicArea = get_model("ThematicArea")
ThematicGroup = get_model("ThematicGroup")
OperationalUnit = get_model("OperationalUnit")

Survey = get_model("Survey")
Question = get_model("Question")
Option = get_model("Option")
Response = get_model("Response")
ResponseHistory = get_model("ResponseHistory")

DashboardWidgetLayout = get_model("DashboardWidgetLayout")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "Category": "layer-group",
    "ThematicArea": "diagram-project",
    "ThematicGroup": "object-group",
    "OperationalUnit": "building",

    "Survey": "clipboard-check",
    "Question": "question-circle",
    "Option": "list-check",
    "Response": "reply",
    "ResponseHistory": "history",

    "DashboardWidgetLayout": "border-all",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "Category": "taxonomy",
    "ThematicArea": "taxonomy",
    "ThematicGroup": "taxonomy",
    "OperationalUnit": "organization",

    "Survey": "analytics",
    "Question": "analytics",
    "Option": "analytics",
    "Response": "analytics",
    "ResponseHistory": "analytics",

    "DashboardWidgetLayout": "dashboard",
}


# ==========================================================
# DISPLAY HELPERS
# ==========================================================
def humanize_model_name(model) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", model.__name__).strip()


def build_meta(model) -> Dict[str, Any]:
    verbose = humanize_model_name(model)

    return {
        "key": f"{model._meta.app_label}.{model._meta.model_name}",
        "app_label": model._meta.app_label,
        "model_name": model._meta.model_name,
        "verbose_name": verbose,
        "verbose_name_plural": f"{verbose}s",
    }


# ==========================================================
# QUERYSET FACTORIES
# ==========================================================

def category_qs(model) -> QuerySet:
    return model.objects.all()


def thematic_area_qs(model) -> QuerySet:
    return model.objects.select_related(
        "category",
    )


def thematic_group_qs(model) -> QuerySet:
    return model.objects.prefetch_related(
        "areas",
    )


def operational_unit_qs(model) -> QuerySet:
    return model.objects.all()


def survey_qs(model) -> QuerySet:
    return model.objects.select_related(
        "unit",
    ).prefetch_related(
        "responses",
    )


def question_qs(model) -> QuerySet:
    return model.objects.select_related(
        "thematic_area",
        "thematic_area__category",
    )


def option_qs(model) -> QuerySet:
    return model.objects.select_related(
        "question",
        "question__thematic_area",
    )


def response_qs(model) -> QuerySet:
    return model.objects.select_related(
        "survey",
        "question",
        "question__thematic_area",
        "self_option",
        "supervisor_option",
        "respondent",
        "supervisor",
    )


def response_history_qs(model) -> QuerySet:
    return model.objects.select_related(
        "response",
        "survey",
        "question",
        "self_option",
        "supervisor_option",
        "user",
    )


def dashboard_layout_qs(model) -> QuerySet:
    return model.objects.select_related(
        "user",
        "unit",
    )


# ==========================================================
# REGISTRY WRAPPER
# ==========================================================
def safe_register(model, **kwargs):
    """
    Registry normalization layer.
    """

    if model is None:
        raise RuntimeError("Model resolution failed.")

    meta = kwargs.get("meta", {})
    meta.update(build_meta(model))
    kwargs["meta"] = meta

    ui = kwargs.get("ui", {})
    ui.setdefault("icon", ICONS.get(model.__name__, "cube"))
    ui.setdefault("group", GROUPS.get(model.__name__, "general"))

    kwargs["ui"] = ui

    kwargs.pop("templates", None)

    try:
        return register_model(**kwargs)(model)
    except Exception:
        logger.exception(
            "[wsp.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# CORE REGISTRATIONS
# ==========================================================

safe_register(
    Category,
    search_fields=["name", "slug"],
    filter_fields=["name"],
    ordering=["name"],
    inline_edit_fields=["name", "slug"],
    queryset_factory=category_qs,
)

safe_register(
    ThematicArea,
    search_fields=["name", "slug", "category__name"],
    filter_fields=["category"],
    ordering=["category__name", "name"],
    select_related=["category"],
    inline_edit_fields=["name", "slug", "category"],
    queryset_factory=thematic_area_qs,
)

safe_register(
    ThematicGroup,
    search_fields=["name"],
    filter_fields=["areas"],
    ordering=["name"],
    prefetch_related=["areas"],
    queryset_factory=thematic_group_qs,
)

safe_register(
    OperationalUnit,
    search_fields=["name", "slug"],
    filter_fields=["name"],
    ordering=["name"],
    inline_edit_fields=["name", "slug"],
    queryset_factory=operational_unit_qs,
)

safe_register(
    Survey,
    search_fields=["name", "slug", "unit__name"],
    filter_fields=["unit", "share_state"],
    ordering=["-created_at"],
    select_related=["unit"],
    prefetch_related=["responses"],
    inline_edit_fields=[
        "name",
        "start_date",
        "end_date",
        "share_state",
        "share_expires_at",
    ],
    queryset_factory=survey_qs,
    bulk_actions={
        "recalculate_average": True,
        "invalidate_cache": True,
    },
)

safe_register(
    Question,
    search_fields=["text", "thematic_area__name"],
    filter_fields=["thematic_area"],
    ordering=["thematic_area__name", "created_at"],
    select_related=["thematic_area", "thematic_area__category"],
    queryset_factory=question_qs,
)

safe_register(
    Option,
    search_fields=["text", "question__text"],
    filter_fields=["question"],
    ordering=["created_at"],
    select_related=["question"],
    queryset_factory=option_qs,
)

safe_register(
    Response,
    search_fields=[
        "survey__name",
        "question__text",
        "respondent__username",
    ],
    filter_fields=[
        "survey",
        "question",
        "respondent",
        "supervisor",
    ],
    ordering=["-created_at"],
    select_related=[
        "survey",
        "question",
        "self_option",
        "supervisor_option",
        "respondent",
        "supervisor",
    ],
    queryset_factory=response_qs,
    bulk_actions={
        "recalculate_survey": True,
        "sync_dashboard": True,
    },
)

safe_register(
    ResponseHistory,
    search_fields=[
        "survey__name",
        "question__text",
        "user__username",
    ],
    filter_fields=[
        "survey",
        "question",
        "user",
    ],
    ordering=["-changed_at"],
    select_related=[
        "response",
        "survey",
        "question",
        "self_option",
        "supervisor_option",
        "user",
    ],
    queryset_factory=response_history_qs,
)

safe_register(
    DashboardWidgetLayout,
    search_fields=["widget_name", "user__username"],
    filter_fields=["user", "unit"],
    ordering=["y", "x"],
    select_related=["user", "unit"],
    queryset_factory=dashboard_layout_qs,
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[wsp.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[wsp.registry] registry unavailable during import"
    )