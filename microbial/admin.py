# microbial/admin.py

from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.db.models import Count, Avg
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    MicrobialSamplingSchedule,
    MicrobialSamplingTime,
    MicrobialAnalysis,
    MicrobialParameterResult,
    TreatedWaterParameterResult,
    MicrobialNonConformity,
    MicrobialAnalysisLog,
    MicrobialNonConformityLog,
    MicrobialAnalysisState,
    NonConformityStatus,
)


# =============================================================================
# BASE ADMIN
# =============================================================================

class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# =============================================================================
# INLINES
# =============================================================================

class SamplingTimeInline(admin.TabularInline):
    model = MicrobialSamplingTime
    extra = 0


class MicrobialParameterInline(admin.TabularInline):
    model = MicrobialParameterResult
    extra = 0
    autocomplete_fields = ("parameter",)
    fields = (
        "parameter",
        "value",
        "manually_editable",
    )


class TreatedWaterParameterInline(admin.TabularInline):
    model = TreatedWaterParameterResult
    extra = 0
    autocomplete_fields = ("parameter",)
    fields = (
        "parameter",
        "value",
        "manually_editable",
    )


class AnalysisLogInline(admin.TabularInline):
    model = MicrobialAnalysisLog
    extra = 0
    readonly_fields = (
        "actor",
        "action",
        "remarks",
        "auto_generated",
        "created_at",
    )
    can_delete = False
    show_change_link = True


class NonConformityLogInline(admin.TabularInline):
    model = MicrobialNonConformityLog
    extra = 0
    readonly_fields = (
        "actor",
        "action",
        "remarks",
        "auto_generated",
        "created_at",
    )
    can_delete = False
    show_change_link = True


# =============================================================================
# SAMPLING SCHEDULE
# =============================================================================

@admin.register(MicrobialSamplingSchedule)
class MicrobialSamplingScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "start_time",
        "interval_minutes",
        "enabled",
        "time_count",
        "last_auto_update",
    )

    list_filter = (
        "enabled",
    )

    inlines = (SamplingTimeInline,)

    list_editable = (
        "enabled",
        "interval_minutes",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                total_times=Count("times")
            )
        )

    def time_count(self, obj):
        return obj.total_times

    time_count.short_description = "Sampling Times"


# =============================================================================
# SAMPLING TIMES
# =============================================================================

@admin.register(MicrobialSamplingTime)
class MicrobialSamplingTimeAdmin(admin.ModelAdmin):
    list_display = (
        "time",
        "schedule",
        "analysis_count",
    )

    list_filter = (
        "schedule",
    )

    search_fields = (
        "time",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                total_analyses=Count("analyses")
            )
        )

    def analysis_count(self, obj):
        return obj.total_analyses

    analysis_count.short_description = "Analyses"


# =============================================================================
# MICROBIAL ANALYSIS
# =============================================================================

@admin.register(MicrobialAnalysis)
class MicrobialAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        "reference_id",
        "treatment_plant",
        "treatment_plant_phase",
        "sampling_time",
        "shift",
        "analysis_date",
        "state_badge",
        "incubation_status",
    )

    list_filter = (
        "state",
        "treatment_plant",
        "treatment_plant_phase",
        "shift",
        ("analysis_date", DateFieldListFilter),
    )

    search_fields = (
        "reference_id",
        "treatment_plant__name",
        "remarks",
    )

    autocomplete_fields = (
        "treatment_plant",
        "treatment_plant_phase",
        "method",
        "shift",
        "sampling_time",
        "analysed_by",
        "verified_by",
        "approved_by",
    )

    readonly_fields = (
        "reference_id",
        "incubation_end",
        "analysed_at",
        "verified_at",
        "approved_at",
        "created_at",
        "updated_at",
    )

    inlines = (
        MicrobialParameterInline,
        TreatedWaterParameterInline,
        AnalysisLogInline,
    )

    date_hierarchy = "analysis_date"

    actions = (
        "mark_analysed",
        "mark_verified",
        "mark_approved",
    )

    fieldsets = (
        (
            "Analysis",
            {
                "fields": (
                    "reference_id",
                    "treatment_plant",
                    "treatment_plant_phase",
                    "method",
                    "shift",
                    "sampling_time",
                    "analysis_date",
                    "state",
                )
            }
        ),
        (
            "Incubation",
            {
                "fields": (
                    "incubation_start",
                    "incubation_end",
                )
            }
        ),
        (
            "Workflow",
            {
                "fields": (
                    "analysed_by",
                    "analysed_at",
                    "verified_by",
                    "verified_at",
                    "approved_by",
                    "approved_at",
                )
            }
        ),
        (
            "Remarks",
            {
                "fields": (
                    "remarks",
                )
            }
        ),
    )

    def state_badge(self, obj):
        colors = {
            "new": "#64748b",
            "analysed": "#2563eb",
            "verified": "#f59e0b",
            "confirmed": "#8b5cf6",
            "approved": "#16a34a",
        }

        return format_html(
            '<span style="background:{};color:white;padding:4px 12px;border-radius:20px;">{}</span>',
            colors.get(obj.state),
            obj.get_state_display(),
        )

    state_badge.short_description = "State"

    def incubation_status(self, obj):
        if not obj.incubation_end:
            return "-"

        if timezone.now() >= obj.incubation_end:
            return format_html(
                '<span style="color:#16a34a;font-weight:bold;">COMPLETE</span>'
            )

        return format_html(
            '<span style="color:#f59e0b;font-weight:bold;">INCUBATING</span>'
        )

    incubation_status.short_description = "Incubation"

    @admin.action(description="Mark selected analyses as analysed")
    def mark_analysed(self, request, queryset):
        queryset.update(
            state=MicrobialAnalysisState.ANALYSED,
            analysed_by=request.user,
            analysed_at=timezone.now(),
        )

    @admin.action(description="Mark selected analyses as verified")
    def mark_verified(self, request, queryset):
        queryset.update(
            state=MicrobialAnalysisState.VERIFIED,
            verified_by=request.user,
            verified_at=timezone.now(),
        )

    @admin.action(description="Mark selected analyses as approved")
    def mark_approved(self, request, queryset):
        queryset.update(
            state=MicrobialAnalysisState.APPROVED,
            approved_by=request.user,
            approved_at=timezone.now(),
        )


# =============================================================================
# MICROBIAL PARAMETER RESULTS
# =============================================================================

@admin.register(MicrobialParameterResult)
class MicrobialParameterResultAdmin(admin.ModelAdmin):
    list_display = (
        "analysis",
        "parameter_name",
        "value",
        "entry_status",
        "manually_editable",
    )

    list_filter = (
        "entry_status",
        "manually_editable",
        "parameter__treatment_plant",
    )

    search_fields = (
        "analysis__reference_id",
        "parameter__parameter__name",
    )

    autocomplete_fields = (
        "analysis",
        "parameter",
    )

    def parameter_name(self, obj):
        return obj.parameter.parameter.name

    parameter_name.short_description = "Parameter"

    def save_model(self, request, obj, form, change):
        if "value" in form.changed_data:
            obj.entry_status = MicrobialParameterResult.EntryStatus.RECORDED
        super().save_model(request, obj, form, change)


# =============================================================================
# TREATED WATER RESULTS
# =============================================================================

@admin.register(TreatedWaterParameterResult)
class TreatedWaterParameterResultAdmin(admin.ModelAdmin):
    list_display = (
        "analysis",
        "parameter_name",
        "value",
        "manually_editable",
    )

    list_filter = (
        "manually_editable",
        "parameter__treatment_plant",
    )

    search_fields = (
        "analysis__reference_id",
        "parameter__parameter__name",
    )

    autocomplete_fields = (
        "analysis",
        "parameter",
    )

    def parameter_name(self, obj):
        return obj.parameter.parameter.name

    parameter_name.short_description = "Parameter"


# =============================================================================
# NONCONFORMITIES
# =============================================================================

@admin.register(MicrobialNonConformity)
class MicrobialNonConformityAdmin(admin.ModelAdmin):
    list_display = (
        "analysis",
        "parameter_name",
        "observed_value",
        "deviation",
        "risk_badge",
        "status_badge",
        "escalation_level",
        "triggered_by",
    )

    list_filter = (
        "status",
        "auto_detected",
        "escalation_level",
        ("created_at", DateFieldListFilter),
    )

    search_fields = (
        "parameter_name",
        "analysis__reference_id",
    )

    autocomplete_fields = (
        "analysis",
        "triggered_by",
    )

    readonly_fields = (
        "risk_score",
        "resolved_at",
    )

    inlines = (
        NonConformityLogInline,
    )

    actions = (
        "evaluate_risk",
        "close_nonconformities",
    )

    def risk_badge(self, obj):
        color = (
            "#16a34a"
            if obj.risk_score < 3
            else "#f59e0b"
            if obj.risk_score < 7
            else "#dc2626"
        )

        return format_html(
            '<span style="background:{};color:white;padding:4px 12px;border-radius:20px;">{}</span>',
            color,
            obj.risk_score,
        )

    risk_badge.short_description = "Risk"

    def status_badge(self, obj):
        colors = {
            "open": "#dc2626",
            "under_review": "#f59e0b",
            "closed": "#16a34a",
        }

        return format_html(
            '<span style="background:{};color:white;padding:4px 12px;border-radius:20px;">{}</span>',
            colors.get(obj.status),
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    @admin.action(description="Recalculate risk scores")
    def evaluate_risk(self, request, queryset):
        for obj in queryset:
            obj.evaluate_risk()

    @admin.action(description="Close selected nonconformities")
    def close_nonconformities(self, request, queryset):
        for obj in queryset.exclude(
            status=NonConformityStatus.CLOSED
        ):
            obj.close(
                actor=request.user,
                remarks="Closed from admin actions."
            )


# =============================================================================
# ANALYSIS LOGS
# =============================================================================

@admin.register(MicrobialAnalysisLog)
class MicrobialAnalysisLogAdmin(ReadOnlyAdmin):
    list_display = (
        "analysis",
        "action",
        "actor",
        "auto_generated",
        "created_at",
    )

    list_filter = (
        "action",
        "auto_generated",
        ("created_at", DateFieldListFilter),
    )

    search_fields = (
        "analysis__reference_id",
        "remarks",
    )

    autocomplete_fields = (
        "analysis",
        "actor",
    )

    date_hierarchy = "created_at"

    ordering = ("-created_at",)


# =============================================================================
# NONCONFORMITY LOGS
# =============================================================================

@admin.register(MicrobialNonConformityLog)
class MicrobialNonConformityLogAdmin(ReadOnlyAdmin):
    list_display = (
        "nonconformity",
        "action",
        "actor",
        "auto_generated",
        "created_at",
    )

    list_filter = (
        "action",
        "auto_generated",
        ("created_at", DateFieldListFilter),
    )

    search_fields = (
        "nonconformity__parameter_name",
        "remarks",
    )

    autocomplete_fields = (
        "nonconformity",
        "actor",
    )

    date_hierarchy = "created_at"

    ordering = ("-created_at",)
