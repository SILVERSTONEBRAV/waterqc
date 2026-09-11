# sc/admin.py
from __future__ import annotations

from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import (
    ShiftSectionRequirement,
    AuditLog,
    Shift,
    ShiftSupervisor,
    ShiftAssignment,
    MonthlyDutyRoster,
    ShiftHandover,
    Apparatus,
    ApparatusCondition,
)


# =============================================================================
# GLOBAL ADMIN SETTINGS
# =============================================================================

class ReadOnlyAdmin(admin.ModelAdmin):
    """Base readonly admin."""

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# =============================================================================
# INLINES
# =============================================================================

class ShiftAssignmentInline(admin.TabularInline):
    model = ShiftAssignment
    extra = 0
    autocomplete_fields = (
        "staff",
        "shift",
        "supervisor",
        "handover_to",
        "temp_supervisor",
    )
    fields = (
        "staff",
        "date",
        "shift",
        "attendance_status",
        "supervisor",
        "handover_to",
    )
    show_change_link = True

class ShiftSectionRequirementInline(admin.TabularInline):
    model = ShiftSectionRequirement
    extra = 0

    autocomplete_fields = (
        "section",
    )

    fields = (
        "section",
        "weekday_required",
        "weekend_required",
        "holiday_required",
        "minimum_required",
        "preferred_required",
        "maximum_allowed",
    )


class ApparatusConditionInline(admin.TabularInline):
    model = ApparatusCondition
    extra = 0
    autocomplete_fields = ("apparatus",)
    fields = (
        "apparatus",
        "status",
        "remarks",
    )
    show_change_link = True


# =============================================================================
# AUDIT LOG
# =============================================================================

@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyAdmin):
    list_display = (
        "timestamp",
        "action_badge",
        "content_type",
        "object_link",
        "user",
    )

    list_filter = (
        "action",
        "content_type",
        ("timestamp", DateFieldListFilter),
    )

    search_fields = (
        "object_id",
        "object_repr",
        "user__username",
        "user__first_name",
        "user__last_name",
    )

    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    fieldsets = (
        (
            "Audit Information",
            {
                "fields": (
                    "timestamp",
                    "user",
                    "action",
                )
            },
        ),
        (
            "Object",
            {
                "fields": (
                    "content_type",
                    "object_id",
                    "object_repr",
                    "changes",
                )
            },
        ),
    )

    readonly_fields = (
        "timestamp",
        "user",
        "action",
        "content_type",
        "object_id",
        "object_repr",
        "changes",
    )

    def action_badge(self, obj):
        colors = {
            "create": "#16a34a",
            "update": "#2563eb",
            "delete": "#dc2626",
        }
        color = colors.get(obj.action, "#64748b")

        return format_html(
            """
            <span style="
                background:{};
                color:white;
                padding:4px 10px;
                border-radius:20px;
                font-weight:600;
            ">
                {}
            </span>
            """,
            color,
            obj.action.upper(),
        )

    action_badge.short_description = "Action"

    def object_link(self, obj):
        return obj.object_repr

    object_link.short_description = "Object"


# =============================================================================
# SHIFT
# =============================================================================

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "treatment_plant",
        "start_time",
        "end_time",
        "assignment_count",
        "is_deleted",
    )

    list_filter = (
        "treatment_plant",
        "is_deleted",
    )

    search_fields = (
        "name",
        "treatment_plant__name",
    )

    autocomplete_fields = ("treatment_plant",)

    ordering = (
        "treatment_plant",
        "start_time",
    )

    readonly_fields = (
        "time_range",
        "assignment_count",
    )

    fieldsets = (
        (
            "General",
            {
                "fields": (
                    "name",
                    "treatment_plant",
                )
            },
        ),
        (
            "Schedule",
            {
                "fields": (
                    "start_time",
                    "end_time",
                    "handover_time",
                    "takeover_time",
                    "time_range",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "assignment_count",
                )
            },
        ),
        (
            "Lifecycle",
            {
                "fields": (
                    "is_deleted",
                    "deleted_at",
                )
            },
        ),
    )
    actions = (
        "soft_delete_selected",
        "restore_selected",)
    inlines = (
        ShiftSectionRequirementInline,
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            assignments_total=Count("assignments")
        )

    def assignment_count(self, obj):
        return getattr(obj, "assignments_total", 0)

    assignment_count.short_description = "Assignments"

    @admin.action(description="Soft delete selected shifts")
    def soft_delete_selected(self, request, queryset):
        count = queryset.update(
            is_deleted=True,
            deleted_at=timezone.now(),
        )
        self.message_user(
            request,
            f"{count} shifts deleted.",
            messages.SUCCESS,
        )

    @admin.action(description="Restore selected shifts")
    def restore_selected(self, request, queryset):
        count = queryset.update(
            is_deleted=False,
            deleted_at=None,
        )
        self.message_user(
            request,
            f"{count} shifts restored.",
            messages.SUCCESS,
        )


# =============================================================================
# SHIFT SUPERVISOR
# =============================================================================

@admin.register(ShiftSupervisor)
class ShiftSupervisorAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "treatment_plant",
        "section",
        "is_active",
    )

    list_filter = (
        "is_active",
        "treatment_plant",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "treatment_plant__name",
    )

    autocomplete_fields = (
        "user",
        "treatment_plant",
    )

    list_editable = ("is_active",)
    list_select_related = (
        "user",
        "treatment_plant",
    )


# =============================================================================
# MONTHLY DUTY ROSTER
# =============================================================================

@admin.register(MonthlyDutyRoster)
class MonthlyDutyRosterAdmin(admin.ModelAdmin):
    list_display = (
        "month",
        "year",
        "treatment_plant",
        "created_by",
        "assignment_total",
        "created_at",
    )

    list_filter = (
        "month",
        "year",
        "treatment_plant",
    )

    search_fields = (
        "treatment_plant__name",
        "notes",
    )

    autocomplete_fields = (
        "treatment_plant",
        "created_by",
    )

    readonly_fields = (
        "created_at",
        "assignment_total",
    )

    inlines = (ShiftAssignmentInline,)

    fieldsets = (
        (
            "Roster",
            {
                "fields": (
                    ("month", "year"),
                    "treatment_plant",
                    "created_by",
                    "notes",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "assignment_total",
                    "created_at",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                assignments_total=Count("assignments")
            )
        )

    def assignment_total(self, obj):
        return getattr(obj, "assignments_total", 0)

    assignment_total.short_description = "Assignments"


# =============================================================================
# SHIFT ASSIGNMENT
# =============================================================================

@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "date",
        "shift",
        "day_type",
        "attendance_badge",
        "supervisor",
        "handover_to",
        "is_deleted",
    )

    list_filter = (
        "attendance_status",
        "day_type",
        "shift",
        "shift__treatment_plant",
        "is_deleted",
        ("date", DateFieldListFilter),
    )

    search_fields = (
        "staff__username",
        "staff__first_name",
        "staff__last_name",
        "remarks",
        "shift__name",
    )

    autocomplete_fields = (
        "staff",
        "shift",
        "duty_roster",
        "supervisor",
        "handover_to",
        "temp_supervisor",
        "reassigned_from",
    )

    date_hierarchy = "date"

    readonly_fields = (
        "week",
        "duration",
        "effective_supervisor",
    )

    list_select_related = (
        "staff",
        "shift",
        "supervisor",
        "handover_to",
    )

    actions = (
        "mark_present",
        "mark_absent",
        "mark_excused",
        "soft_delete_assignments",
    )

    fieldsets = (
        (
            "Assignment",
            {
                "fields": (
                    "staff",
                    "shift",
                    "date",
                    "duty_roster",
                    "day_type",
                )
            },
        ),
        (
            "Attendance",
            {
                "fields": (
                    "attendance_status",
                    "remarks",
                )
            },
        ),
        (
            "Supervision",
            {
                "fields": (
                    "supervisor",
                    "effective_supervisor",
                    "temp_supervisor",
                    "temp_supervisor_start",
                    "temp_supervisor_end",
                )
            },
        ),
        (
            "Handover",
            {
                "fields": (
                    "handover_to",
                    "reassigned_from",
                    "reassigned_at",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "week",
                    "duration",
                )
            },
        ),
    )

    def attendance_badge(self, obj):
        colors = {
            "present": "#16a34a",
            "absent": "#dc2626",
            "late": "#f59e0b",
            "excused": "#2563eb",
        }

        return format_html(
            """
            <span style="
                background:{};
                color:white;
                padding:4px 12px;
                border-radius:20px;
                font-weight:600;
            ">
                {}
            </span>
            """,
            colors.get(obj.attendance_status, "#64748b"),
            obj.get_attendance_status_display(),
        )

    attendance_badge.short_description = "Attendance"

    @admin.action(description="Mark selected as PRESENT")
    def mark_present(self, request, queryset):
        queryset.update(
            attendance_status=ShiftAssignment.ATTENDANCE_PRESENT
        )

    @admin.action(description="Mark selected as ABSENT")
    def mark_absent(self, request, queryset):
        queryset.update(
            attendance_status=ShiftAssignment.ATTENDANCE_ABSENT
        )

    @admin.action(description="Mark selected as EXCUSED")
    def mark_excused(self, request, queryset):
        queryset.update(
            attendance_status=ShiftAssignment.ATTENDANCE_EXCUSED
        )

    @admin.action(description="Soft delete assignments")
    def soft_delete_assignments(self, request, queryset):
        queryset.update(
            is_deleted=True,
            deleted_at=timezone.now(),
        )


@admin.register(ShiftSectionRequirement)
class ShiftSectionRequirementAdmin(admin.ModelAdmin):
    list_display = (
        "shift",
        "section",
        "weekday_required",
        "weekend_required",
        "holiday_required",
        "minimum_required",
        "preferred_required",
        "maximum_allowed",
    )

    list_filter = (
        "shift",
        "section",
    )

    search_fields = (
        "shift__name",
        "section__name",
    )

    autocomplete_fields = (
        "shift",
        "section",
    )

    list_select_related = (
        "shift",
        "section",
    )

@admin.register(ShiftHandover)
class ShiftHandoverAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "shift",
        "outgoing_supervisor",
        "incoming_supervisor",
        "is_taken_over",
        "taken_over_at",
    )

    list_filter = (
        "is_taken_over",
        "shift",
        ("date", DateFieldListFilter),
    )

    search_fields = (
        "shift__name",
        "handover_notes",
        "pending_work",
        "outgoing_supervisor__username",
        "incoming_supervisor__username",
    )

    autocomplete_fields = (
        "shift",
        "outgoing_supervisor",
        "incoming_supervisor",
    )

    date_hierarchy = "date"

    inlines = (ApparatusConditionInline,)

    readonly_fields = (
        "handed_over_at",
    )
    list_select_related = (
        "shift",
        "incoming_supervisor",
        "outgoing_supervisor",
    )


# =============================================================================
# APPARATUS
# =============================================================================

@admin.register(Apparatus)
class ApparatusAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "equipment",
        "equipment_status",
    )

    search_fields = (
        "name",
        "equipment__name",
    )

    autocomplete_fields = ("equipment",)

    def equipment_status(self, obj):
        if not obj.equipment or not obj.equipment.status:
            return "-"

        return obj.equipment.status.name

    equipment_status.short_description = "Equipment Status"


# =============================================================================
# APPARATUS CONDITION
# =============================================================================

@admin.register(ApparatusCondition)
class ApparatusConditionAdmin(admin.ModelAdmin):
    list_display = (
        "apparatus",
        "handover",
        "status_badge",
    )

    list_filter = (
        "status",
        "handover__shift",
    )

    search_fields = (
        "apparatus__name",
        "remarks",
    )

    autocomplete_fields = (
        "handover",
        "apparatus",
    )

    def status_badge(self, obj):
        colors = {
            "working": "#16a34a",
            "needs_repair": "#f59e0b",
            "out_of_service": "#dc2626",
        }

        return format_html(
            """
            <span style="
                background:{};
                color:white;
                padding:4px 12px;
                border-radius:20px;
                font-weight:600;
            ">
                {}
            </span>
            """,
            colors.get(obj.status, "#64748b"),
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"