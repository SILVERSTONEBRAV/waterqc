# wsp/admin.py

from decimal import Decimal
import json

from django.contrib import admin, messages
from django.db.models import (
    Avg,
    Count,
    Sum,
    F,
    Q,
)
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import (
    Category,
    ThematicArea,
    ThematicGroup,
    OperationalUnit,
    Survey,
    Question,
    Option,
    Response,
    ResponseHistory,
    DashboardWidgetLayout,
)


###########################################################################
# UTILITIES
###########################################################################

def badge(text, color):
    return format_html(
        """
        <span style="
            background:{};
            color:white;
            padding:4px 10px;
            border-radius:15px;
            font-weight:600;
            font-size:12px;
        ">
            {}
        </span>
        """,
        color,
        text,
    )


def progress_bar(value):
    value = float(value or 0)

    if value < 30:
        color = "#dc3545"
    elif value < 70:
        color = "#ffc107"
    else:
        color = "#198754"

    return format_html(
        """
        <div style="
            width:140px;
            background:#e9ecef;
            border-radius:20px;
            overflow:hidden;
        ">
            <div style="
                width:{}%;
                background:{};
                color:white;
                text-align:center;
                padding:3px;
                font-weight:bold;
            ">
                {}%
            </div>
        </div>
        """,
        value,
        color,
        round(value, 2),
    )


###########################################################################
# FILTERS
###########################################################################

class ActiveFilter(admin.SimpleListFilter):
    title = _("Status")
    parameter_name = "active"

    def lookups(self, request, model_admin):
        return (
            ("1", "Active"),
            ("0", "Inactive"),
        )

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(is_active=True)

        if self.value() == "0":
            return queryset.filter(is_active=False)

        return queryset


###########################################################################
# INLINES
###########################################################################

class OptionInline(admin.TabularInline):
    model = Option
    extra = 1
    autocomplete_fields = ()
    fields = (
        "text",
        "score",
        "color",
    )


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    show_change_link = True


class ResponseInline(admin.TabularInline):
    model = Response
    extra = 0
    autocomplete_fields = (
        "self_option",
        "supervisor_option",
        "respondent",
        "supervisor",
    )
    show_change_link = True


class ResponseHistoryInline(admin.TabularInline):
    model = ResponseHistory
    extra = 0
    can_delete = False
    readonly_fields = (
        "question",
        "self_option",
        "supervisor_option",
        "user",
        "changed_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


###########################################################################
# CATEGORY
###########################################################################

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "areas_count",
        "average_score_display",
        "is_active",
    )

    search_fields = (
        "name",
        "slug",
    )

    list_filter = (
        ActiveFilter,
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "meta_pretty",
    )

    actions = (
        "activate",
        "deactivate",
    )

    def areas_count(self, obj):
        return obj.areas.count()

    def average_score_display(self, obj):
        score = obj.average_score()
        return badge(round(score, 2), "#0d6efd")

    def meta_pretty(self, obj):
        return format_html(
            "<pre>{}</pre>",
            json.dumps(obj.meta, indent=4),
        )

    @admin.action(description="Activate selected")
    def activate(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Deactivate selected")
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)


###########################################################################
# THEMATIC AREA
###########################################################################

@admin.register(ThematicArea)
class ThematicAreaAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "question_count",
        "average_score_display",
        "is_active",
    )

    list_filter = (
        "category",
        ActiveFilter,
    )

    search_fields = (
        "name",
        "category__name",
    )

    inlines = [
        QuestionInline,
    ]

    def question_count(self, obj):
        return obj.questions.count()

    def average_score_display(self, obj):
        score = obj.average_score()
        return badge(round(score, 2), "#20c997")


###########################################################################
# THEMATIC GROUP
###########################################################################

@admin.register(ThematicGroup)
class ThematicGroupAdmin(admin.ModelAdmin):
    filter_horizontal = ("areas",)

    list_display = (
        "name",
        "areas_count",
        "average_score_display",
    )

    search_fields = ("name",)

    def areas_count(self, obj):
        return obj.areas.count()

    def average_score_display(self, obj):
        return badge(obj.average_score(), "#6610f2")


###########################################################################
# OPERATIONAL UNIT
###########################################################################

@admin.register(OperationalUnit)
class OperationalUnitAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "survey_count",
        "is_active",
    )

    search_fields = (
        "name",
        "slug",
    )

    list_filter = (
        ActiveFilter,
    )

    def survey_count(self, obj):
        return obj.surveys.count()


###########################################################################
# OPTION
###########################################################################

@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = (
        "text",
        "question",
        "score",
        "color_preview",
    )

    search_fields = (
        "text",
        "question__text",
    )

    list_filter = (
        "question__thematic_area",
    )

    def color_preview(self, obj):
        return format_html(
            """
            <div style="
                width:40px;
                height:20px;
                background:{};
                border-radius:4px;
                border:1px solid #ddd;
            ">
            </div>
            """,
            obj.color,
        )


###########################################################################
# QUESTION
###########################################################################

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        "short_text",
        "thematic_area",
        "weight",
        "option_count",
    )

    search_fields = (
        "text",
        "thematic_area__name",
    )

    list_filter = (
        "thematic_area",
    )

    inlines = [
        OptionInline,
    ]

    def short_text(self, obj):
        return obj.text[:80]

    def option_count(self, obj):
        return obj.options.count()


###########################################################################
# SURVEY
###########################################################################

@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "unit",
        "average_score_badge",
        "completion_display",
        "share_status",
        "created_at",
    )

    list_filter = (
        "unit",
        "share_state",
        "created_at",
    )

    search_fields = (
        "name",
        "unit__name",
    )

    autocomplete_fields = (
        "unit",
    )

    readonly_fields = (
        "id",
        "slug",
        "average_score",
        "completion_display",
        "share_uuid",
        "created_at",
        "updated_at",
    )

    inlines = [
        ResponseInline,
    ]

    date_hierarchy = "created_at"

    def average_score_badge(self, obj):
        return badge(obj.average_score, "#198754")

    def completion_display(self, obj):
        return progress_bar(obj.completion_rate)

    def share_status(self, obj):
        if obj.share_state == "public":
            return badge("PUBLIC", "#198754")
        return badge("DISABLED", "#6c757d")


###########################################################################
# RESPONSE HISTORY
###########################################################################

@admin.register(ResponseHistory)
class ResponseHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "response",
        "question",
        "user",
        "changed_at",
    )

    search_fields = (
        "question__text",
        "user__username",
    )

    readonly_fields = (
        "response",
        "survey",
        "question",
        "self_option",
        "supervisor_option",
        "user",
        "changed_at",
    )

    date_hierarchy = "changed_at"

    def has_add_permission(self, request):
        return False


###########################################################################
# RESPONSE
###########################################################################

@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = (
        "survey",
        "question_short",
        "respondent",
        "supervisor",
        "score_display",
        "completed_at",
    )

    list_filter = (
        "survey",
        "question__thematic_area",
        "completed_at",
    )

    search_fields = (
        "survey__name",
        "question__text",
        "respondent__username",
    )

    autocomplete_fields = (
        "survey",
        "question",
        "self_option",
        "supervisor_option",
        "respondent",
        "supervisor",
    )

    readonly_fields = (
        "average_score_display",
        "completed_at",
    )

    inlines = [
        ResponseHistoryInline,
    ]

    date_hierarchy = "completed_at"

    def question_short(self, obj):
        return obj.question.text[:80]

    def score_display(self, obj):
        score = obj.average_score
        color = "#198754"

        if score < 2:
            color = "#dc3545"
        elif score < 3:
            color = "#ffc107"

        return badge(round(score, 2), color)

    def average_score_display(self, obj):
        return badge(round(obj.average_score, 2), "#0d6efd")


###########################################################################
# DASHBOARD LAYOUT
###########################################################################

@admin.register(DashboardWidgetLayout)
class DashboardWidgetLayoutAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "unit",
        "widget_name",
        "position",
        "size",
        "collapsed",
        "updated_at",
    )

    list_filter = (
        "unit",
        "collapsed",
    )

    search_fields = (
        "user__username",
        "widget_name",
    )

    autocomplete_fields = (
        "user",
        "unit",
    )

    readonly_fields = (
        "updated_at",
    )

    def position(self, obj):
        return f"({obj.x}, {obj.y})"

    def size(self, obj):
        return f"{obj.width} × {obj.height}"