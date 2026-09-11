from django.shortcuts import render

# Create your views here.
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .models import (
    SamplingSchedule, SamplingTime,
    WaterAnalysis, WaterAnalysisLog,
    TreatedWaterResult, RawWaterResult, CoagulatedWaterResult, ClarifiedWaterResult,
    NonConformity, NonConformityLog, Cause,
    WaterAnalysisState, NonConformityStatus,
    TreatedWaterLimit, RawWaterLimit, CoagulatedWaterLimit, ClarifiedWaterLimit,
)


# ==========================================================
# 🧩 UTILITIES
# ==========================================================

def color_badge(text, color):
    return format_html(
        '<span style="background:{};color:white;padding:2px 6px;border-radius:6px;font-weight:500;">{}</span>',
        color, text
    )


def state_color(state):
    return {
        "new": "#7f8c8d",
        "analysed": "#3498db",
        "verified": "#f1c40f",
        "confirmed": "#1abc9c",
        "approved": "#2ecc71",
    }.get(state, "#95a5a6")


def status_color(status):
    return {
        "open": "#e74c3c",
        "under_review": "#f39c12",
        "closed": "#27ae60",
        "escalated": "#8e44ad",
    }.get(status, "#7f8c8d")


# ==========================================================
# 🔍 FILTERS
# ==========================================================

class StateFilter(admin.SimpleListFilter):
    title = _("Analysis State")
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return WaterAnalysisState.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(state=self.value())
        return queryset


class NonConformityStatusFilter(admin.SimpleListFilter):
    title = _("NC Status")
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return NonConformityStatus.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


# ==========================================================
# ⏱ SAMPLING ADMIN
# ==========================================================

@admin.register(SamplingSchedule)
class SamplingScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "water_type", "start_time", "interval_minutes",
        "enabled_toggle", "adaptive_badge", "adaptive_confidence", "last_auto_update",
    )
    list_editable = ("interval_minutes",)
    list_filter = ("enabled", "adaptive", "water_type")
    search_fields = ("water_type",)
    actions = ["generate_sampling_times", "toggle_adaptive", "enable_selected", "disable_selected"]
    ordering = ("water_type",)
    readonly_fields = ("last_auto_update",)

    def enabled_toggle(self, obj):
        color = "green" if obj.enabled else "red"
        label = "Enabled" if obj.enabled else "Disabled"
        return format_html(f'<b style="color:{color};font-weight:600;">{label}</b>')

    enabled_toggle.short_description = "Enabled"

    def adaptive_badge(self, obj):
        return color_badge("Adaptive", "#16a085") if obj.adaptive else "—"

    adaptive_badge.short_description = "Adaptive"

    @admin.action(description="⚙️ Generate Sampling Times for selected schedules")
    def generate_sampling_times(self, request, queryset):
        for s in queryset:
            s.generate_times()
        self.message_user(request, f"✅ Generated sampling times for {queryset.count()} schedule(s).", messages.SUCCESS)

    @admin.action(description="🔄 Toggle Adaptive Mode")
    def toggle_adaptive(self, request, queryset):
        for s in queryset:
            s.adaptive = not s.adaptive
            s.save()
        self.message_user(request, f"Toggled adaptive mode for {queryset.count()} schedule(s).", messages.INFO)

    @admin.action(description="🟢 Enable selected schedules")
    def enable_selected(self, request, queryset):
        updated = queryset.update(enabled=True)
        self.message_user(request, f"Enabled {updated} schedule(s).", messages.SUCCESS)

    @admin.action(description="🔴 Disable selected schedules")
    def disable_selected(self, request, queryset):
        updated = queryset.update(enabled=False)
        self.message_user(request, f"Disabled {updated} schedule(s).", messages.WARNING)


@admin.register(SamplingTime)
class SamplingTimeAdmin(admin.ModelAdmin):
    list_display = ("display_name", "formatted_time", "water_type_badge")
    list_filter = ("water_type",)
    search_fields = ("name",)
    ordering = ("time",)

    def display_name(self, obj):
        return obj.name or f"{obj.get_water_type_display()} Water"

    display_name.short_description = "Name"

    def formatted_time(self, obj):
        return obj.time.strftime("%I:%M %p").lower() if obj.time else "—"

    formatted_time.short_description = "Time"

    def water_type_badge(self, obj):
        color_map = {
            "treated": "#3498db",
            "raw": "#e67e22",
            "clarified": "#8e44ad",
            "coagulated": "#16a085",
        }
        color = color_map.get(str(obj.water_type), "#7f8c8d")
        return color_badge(obj.get_water_type_display(), color)

    water_type_badge.short_description = "Water Type"


# ==========================================================
# 💧 INLINE DEFINITIONS — Dynamic Parameter Inlines
# ==========================================================
class BaseWaterResultInline(admin.TabularInline):
    """Dynamic inline showing all parameters for a water type."""
    extra = 0
    can_delete = False
    readonly_fields = ("parameter_display", "unit_display", "status_display")  # value is now editable
    fields = ("parameter_display", "value", "unit_display", "status_display")  # admin shows editable value
    ordering = ("parameter__parameter",)
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return True

    def get_expected_parameters(self, analysis):
        """Override in subclass to return queryset of parameter limits."""
        return []

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("parameter")

    def get_formset(self, request, obj=None, **kwargs):
        FormSet = super().get_formset(request, obj, **kwargs)
        if not obj:
            return FormSet
        expected = self.get_expected_parameters(obj)
        existing_ids = self.model.objects.filter(analysis=obj).values_list("parameter_id", flat=True)
        missing = [p for p in expected if p.id not in existing_ids]
        for p in missing:
            self.model.objects.get_or_create(analysis=obj, parameter=p, defaults={"value": 0.0})
        return FormSet

    # Display helpers
    def parameter_display(self, obj):
        return str(getattr(getattr(obj, "parameter", None), "parameter", obj.parameter) or "—")
    parameter_display.short_description = "Parameter"

    def unit_display(self, obj):
        param = getattr(getattr(obj, "parameter", None), "parameter", None)
        return getattr(param, "unit", "—")
    unit_display.short_description = "Unit"

    def status_display(self, obj):
        if hasattr(obj, "nonconformity_set") and obj.nonconformity_set.exists():
            return color_badge("⚠️ Non-Conforming", "#e74c3c")
        return color_badge("✅ OK", "#27ae60")
    status_display.short_description = "Status"

    def save_new_objects(self, form, commit=True):
        """Ensure detect_nonconformity triggers after admin save."""
        instance = form.save(commit=False)
        instance.save()
        if commit:
            instance.save()
            detect_nonconformity(instance.parameter, instance.value, instance.analysis, instance.analysis.analysed_by)
        return instance

    def save_existing(self, form, instance, commit=True):
        instance = form.save(commit=False)
        if commit:
            instance.save()
            detect_nonconformity(instance.parameter, instance.value, instance.analysis, instance.analysis.analysed_by)
        return instance



class TreatedWaterResultInline(BaseWaterResultInline):
    model = TreatedWaterResult
    verbose_name_plural = "Treated Water Results"

    def get_expected_parameters(self, analysis):
        return list(TreatedWaterLimit.objects.filter(treatment_plant=analysis.treatment_plant))


class RawWaterResultInline(BaseWaterResultInline):
    model = RawWaterResult
    verbose_name_plural = "Raw Water Results"

    def get_expected_parameters(self, analysis):
        return list(RawWaterLimit.objects.filter(treatment_plant=analysis.treatment_plant))


class ClarifiedWaterResultInline(BaseWaterResultInline):
    model = ClarifiedWaterResult
    verbose_name_plural = "Clarified Water Results"

    def get_expected_parameters(self, analysis):
        return list(ClarifiedWaterLimit.objects.filter(treatment_plant=analysis.treatment_plant))


class CoagulatedWaterResultInline(BaseWaterResultInline):
    model = CoagulatedWaterResult
    verbose_name_plural = "Coagulated Water Results"

    def get_expected_parameters(self, analysis):
        return list(CoagulatedWaterLimit.objects.filter(treatment_plant=analysis.treatment_plant))


# ==========================================================
# 🔍 READ-ONLY INLINES (Logs / Non-Conformities)
# ==========================================================

class ReadOnlyNonConformityInline(admin.TabularInline):
    model = NonConformity
    extra = 0
    can_delete = False
    readonly_fields = ("parameter_name", "deviation", "status_colored", "auto_detected", "resolved_at")
    show_change_link = True
    verbose_name_plural = "Non-Conformities"

    def has_add_permission(self, request, obj=None):
        return False

    def status_colored(self, obj):
        return color_badge(obj.get_status_display(), status_color(obj.status))

    status_colored.short_description = "Status"


class ReadOnlyWaterAnalysisLogInline(admin.TabularInline):
    model = WaterAnalysisLog
    extra = 0
    can_delete = False
    readonly_fields = ("created_at", "actor", "action", "remarks", "auto_generated")
    verbose_name_plural = "Audit Trail"

    def has_add_permission(self, request, obj=None):
        return False


# ==========================================================
# 💧 WATER ANALYSIS ADMIN
# ==========================================================

@admin.register(WaterAnalysis)
class WaterAnalysisAdmin(admin.ModelAdmin):
    list_display = ("reference_id", "treatment_plant", "state_colored", "shift", "created_at")
    list_filter = ("treatment_plant", "shift", StateFilter)
    search_fields = ("reference_id", "treatment_plant__name", "treatment_plant_phase__name")
    ordering = ("-created_at",)
    list_select_related = ("treatment_plant", "shift")
    autocomplete_fields = ("treatment_plant", "treatment_plant_phase", "shift", "analysis_time")
    readonly_fields = ("reference_id", "created_at", "updated_at")
    actions = ["mark_as_verified", "mark_as_approved"]

    def get_inline_instances(self, request, obj=None):
        inlines = [
            TreatedWaterResultInline(self.model, self.admin_site),
            RawWaterResultInline(self.model, self.admin_site),
            ClarifiedWaterResultInline(self.model, self.admin_site),
            CoagulatedWaterResultInline(self.model, self.admin_site),
            ReadOnlyNonConformityInline(self.model, self.admin_site),
            ReadOnlyWaterAnalysisLogInline(self.model, self.admin_site),
        ]
        return inlines

    def state_colored(self, obj):
        return color_badge(obj.get_state_display(), state_color(obj.state))

    state_colored.short_description = "State"

    @admin.action(description="✅ Mark selected as Verified")
    def mark_as_verified(self, request, queryset):
        count = queryset.filter(state=WaterAnalysisState.ANALYSED).update(
            state=WaterAnalysisState.VERIFIED, verified_at=timezone.now()
        )
        self.message_user(request, f"Marked {count} analyses as VERIFIED.", messages.SUCCESS)

    @admin.action(description="🟩 Approve selected Analyses")
    def mark_as_approved(self, request, queryset):
        count = queryset.filter(state__in=[WaterAnalysisState.VERIFIED, WaterAnalysisState.CONFIRMED]).update(
            state=WaterAnalysisState.APPROVED, approved_at=timezone.now()
        )
        self.message_user(request, f"Approved {count} analyses.", messages.SUCCESS)


# ==========================================================
# 🚨 NON-CONFORMITY ADMIN
# ==========================================================

class NonConformityLogInline(admin.TabularInline):
    model = NonConformityLog
    extra = 0
    readonly_fields = ("created_at", "actor", "action", "remarks", "auto_generated")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(NonConformity)
class NonConformityAdmin(admin.ModelAdmin):
    list_display = (
        "parameter_name", "status_colored", "deviation",
        "auto_detected", "analysis", "triggered_by", "created_at"
    )
    list_filter = (NonConformityStatusFilter, "auto_detected")
    search_fields = ("parameter_name", "analysis__reference_id", "triggered_by__username")
    autocomplete_fields = ("analysis", "causes", "triggered_by")
    readonly_fields = ("created_at", "updated_at")
    inlines = [NonConformityLogInline]
    actions = ["close_selected", "escalate_selected"]

    def has_add_permission(self, request):
        return False

    def status_colored(self, obj):
        return color_badge(obj.get_status_display(), status_color(obj.status))

    status_colored.short_description = "Status"

    @admin.action(description="✅ Close selected Non-Conformities")
    def close_selected(self, request, queryset):
        count = queryset.filter(status__in=["open", "under_review"]).update(
            status="closed", resolved_at=timezone.now()
        )
        self.message_user(request, f"Closed {count} Non-Conformities.", messages.SUCCESS)

    @admin.action(description="⚠️ Escalate selected Non-Conformities")
    def escalate_selected(self, request, queryset):
        count = queryset.filter(status__in=["open", "under_review"]).update(status="escalated")
        self.message_user(request, f"Escalated {count} Non-Conformities.", messages.WARNING)


# ==========================================================
# 🔬 CAUSE ADMIN
# ==========================================================

@admin.register(Cause)
class CauseAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "created_by", "created_at")
    search_fields = ("name", "description")
    autocomplete_fields = ("created_by",)
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")
