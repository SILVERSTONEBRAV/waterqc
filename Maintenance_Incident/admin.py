# Maintenance_Incident/admin.py

import json
from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.db.models import (
    Count,
    Avg,
    Q,
    F,
    ExpressionWrapper,
    DurationField,
)
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import (
    IncidentEscalationRule,
    IncidentCluster,
    EquipmentHealthScore,
    MaintenanceIncident,
    IncidentStream,
    IncidentSeverity,
    IncidentStatus,
)


# ============================================================
# BASE ADMIN
# ============================================================

class BaseAdmin(admin.ModelAdmin):
    save_on_top = True
    show_full_result_count = True

    readonly_fields = (
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user

        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================
# COMMON HELPERS
# ============================================================

def badge(label, color):
    return format_html(
        """
        <span style="
            background:{};
            color:white;
            padding:4px 12px;
            border-radius:20px;
            font-weight:600;
            display:inline-block;
        ">
            {}
        </span>
        """,
        color,
        label,
    )


def progress_bar(percent, color):
    percent = max(0, min(int(percent), 100))

    return format_html(
        """
        <div style="
            width:140px;
            background:#e5e7eb;
            border-radius:10px;
            overflow:hidden;
        ">
            <div style="
                width:{}%;
                background:{};
                color:white;
                text-align:center;
                padding:2px;
            ">
                {}%
            </div>
        </div>
        """,
        percent,
        color,
        percent,
    )


# ============================================================
# INLINE
# ============================================================

class IncidentStreamInline(admin.TabularInline):
    model = IncidentStream
    extra = 0
    can_delete = False

    readonly_fields = (
        "event_type",
        "payload_pretty",
        "severity_snapshot",
        "created_at",
    )

    fields = (
        "event_type",
        "severity_snapshot",
        "payload_pretty",
        "created_at",
    )

    def payload_pretty(self, obj):
        return format_html(
            "<pre>{}</pre>",
            json.dumps(obj.payload, indent=2),
        )

    payload_pretty.short_description = "Payload"


# ============================================================
# ESCALATION RULES
# ============================================================

@admin.register(IncidentEscalationRule)
class IncidentEscalationRuleAdmin(BaseAdmin):
    list_display = (
        "name",
        "severity_display",
        "incident_type",
        "escalate_after_minutes",
        "auto_assign_supervisor",
        "auto_create_workorder",
        "is_active",
    )

    list_editable = (
        "escalate_after_minutes",
        "auto_assign_supervisor",
        "auto_create_workorder",
        "is_active",
    )

    list_filter = (
        "severity",
        "incident_type",
        "is_active",
        "auto_assign_supervisor",
        "auto_create_workorder",
    )

    search_fields = ("name",)

    def severity_display(self, obj):
        colors = {
            "low": "#16a34a",
            "medium": "#2563eb",
            "high": "#f59e0b",
            "critical": "#dc2626",
        }

        return badge(
            obj.get_severity_display(),
            colors[obj.severity],
        )

    severity_display.short_description = "Severity"


# ============================================================
# INCIDENT CLUSTERS
# ============================================================

@admin.register(IncidentCluster)
class IncidentClusterAdmin(BaseAdmin):
    list_display = (
        "title",
        "incident_type",
        "incident_count",
        "frequency_score",
        "risk_score",
        "last_seen_at",
    )

    search_fields = (
        "title",
        "cluster_key",
    )

    list_filter = (
        "incident_type",
        ("last_seen_at", DateFieldListFilter),
    )

    readonly_fields = (
        "cluster_key",
        "predicted_risk_score",
        "frequency_score",
        "last_seen_at",
        "incident_count",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                total_incidents=Count("incidents")
            )
        )

    def incident_count(self, obj):
        return obj.total_incidents

    def risk_score(self, obj):
        return progress_bar(
            obj.predicted_risk_score * 100,
            "#dc2626",
        )

    risk_score.short_description = "Risk"


# ============================================================
# EQUIPMENT HEALTH
# ============================================================

@admin.register(EquipmentHealthScore)
class EquipmentHealthScoreAdmin(BaseAdmin):
    list_display = (
        "equipment",
        "health_score",
        "failure_risk",
        "last_updated",
    )

    search_fields = (
        "equipment__name",
        "equipment__serial_number",
    )

    autocomplete_fields = (
        "equipment",
    )

    readonly_fields = (
        "score",
        "failure_risk",
        "last_updated",
    )

    def health_score(self, obj):
        color = (
            "#16a34a"
            if obj.score >= 70
            else "#f59e0b"
            if obj.score >= 40
            else "#dc2626"
        )

        return progress_bar(
            obj.score,
            color,
        )

    def failure_risk(self, obj):
        return progress_bar(
            obj.failure_risk * 100,
            "#dc2626",
        )

    failure_risk.short_description = "Failure Risk"


# ============================================================
# INCIDENT ADMIN
# ============================================================

@admin.register(MaintenanceIncident)
class MaintenanceIncidentAdmin(BaseAdmin):
    date_hierarchy = "reported_at"

    list_display = (
        "incident_no",
        "title",
        "severity_display",
        "status_display",
        "incident_type",
        "plant",
        "equipment",
        "reported_by",
        "incident_age",
        "duplicate_count",
    )

    list_select_related = (
        "reported_by",
        "equipment",
        "plant",
        "cluster",
    )

    search_fields = (
        "incident_no",
        "title",
        "description",
        "fingerprint",
        "equipment__name",
        "reported_by__username",
    )

    autocomplete_fields = (
        "reported_by",
        "equipment",
        "plant",
        "duty_house",
        "cluster",
        "work_request",
        "work_order",
    )

    list_filter = (
        "severity",
        "status",
        "incident_type",
        "plant",
        ("occurred_at", DateFieldListFilter),
        ("reported_at", DateFieldListFilter),
    )

    readonly_fields = (
        "fingerprint",
        "reported_at",
        "estimated_impact_score",
        "sla_breach_time",
        "metadata_pretty",
        "incident_age",
    )

    inlines = (
        IncidentStreamInline,
    )

    actions = (
        "process_incidents",
        "auto_dispatch_selected",
        "mark_resolved",
        "mark_closed",
        "mark_under_review",
    )

    fieldsets = (
        (
            "Incident Information",
            {
                "fields": (
                    "incident_no",
                    "title",
                    "description",
                    ("incident_type", "severity"),
                    ("status", "target_type"),
                )
            },
        ),
        (
            "Location",
            {
                "classes": ("collapse",),
                "fields": (
                    "plant",
                    "duty_house",
                    "equipment",
                ),
            },
        ),
        (
            "Reporting",
            {
                "classes": ("collapse",),
                "fields": (
                    "reported_by",
                    "occurred_at",
                    "reported_at",
                    "incident_age",
                ),
            },
        ),
        (
            "Analytics",
            {
                "classes": ("collapse",),
                "fields": (
                    "cluster",
                    "fingerprint",
                    "estimated_impact_score",
                    "sla_breach_time",
                    "metadata_pretty",
                ),
            },
        ),
        (
            "Maintenance Integration",
            {
                "classes": ("collapse",),
                "fields": (
                    "work_request",
                    "work_order",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                duplicates=Count(
                    "cluster__incidents"
                )
            )
        )

    def metadata_pretty(self, obj):
        return format_html(
            "<pre>{}</pre>",
            json.dumps(
                obj.metadata,
                indent=2,
            ),
        )

    metadata_pretty.short_description = "Metadata"

    def duplicate_count(self, obj):
        if not obj.cluster:
            return "-"

        return badge(
            str(obj.duplicates),
            "#7c3aed",
        )

    def incident_age(self, obj):
        age = timezone.now() - obj.occurred_at
        return str(age).split(".")[0]

    incident_age.short_description = "Age"

    def severity_display(self, obj):
        colors = {
            "low": "#16a34a",
            "medium": "#2563eb",
            "high": "#f59e0b",
            "critical": "#dc2626",
        }

        return badge(
            obj.get_severity_display(),
            colors[obj.severity],
        )

    severity_display.short_description = "Severity"

    def status_display(self, obj):
        colors = {
            "reported": "#64748b",
            "under_review": "#3b82f6",
            "confirmed": "#16a34a",
            "escalated": "#dc2626",
            "converted": "#7c3aed",
            "auto_dispatched": "#be123c",
            "resolved": "#15803d",
            "closed": "#334155",
        }

        return badge(
            obj.get_status_display(),
            colors.get(obj.status, "#64748b"),
        )

    status_display.short_description = "Status"

    # ====================================================
    # ACTIONS
    # ====================================================

    @admin.action(description="Process incidents")
    def process_incidents(self, request, queryset):
        count = 0

        for incident in queryset:
            incident.process_incident()
            count += 1

        self.message_user(
            request,
            f"{count} incidents processed.",
            messages.SUCCESS,
        )

    @admin.action(description="Auto dispatch")
    def auto_dispatch_selected(
        self,
        request,
        queryset,
    ):
        count = 0

        for incident in queryset.filter(
            severity=IncidentSeverity.CRITICAL
        ):
            if not incident.work_order:
                incident.auto_dispatch()
                count += 1

        self.message_user(
            request,
            f"{count} incidents dispatched.",
            messages.SUCCESS,
        )

    @admin.action(description="Mark resolved")
    def mark_resolved(
        self,
        request,
        queryset,
    ):
        queryset.update(
            status=IncidentStatus.RESOLVED
        )

    @admin.action(description="Mark closed")
    def mark_closed(
        self,
        request,
        queryset,
    ):
        queryset.update(
            status=IncidentStatus.CLOSED
        )

    @admin.action(description="Mark under review")
    def mark_under_review(
        self,
        request,
        queryset,
    ):
        queryset.update(
            status=IncidentStatus.UNDER_REVIEW
        )


# ============================================================
# EVENT STREAM
# ============================================================

@admin.register(IncidentStream)
class IncidentStreamAdmin(ReadOnlyAdmin):
    list_display = (
        "incident",
        "event_type",
        "severity_snapshot",
        "created_at",
    )

    list_filter = (
        "event_type",
        "severity_snapshot",
        ("created_at", DateFieldListFilter),
    )

    search_fields = (
        "incident__incident_no",
        "event_type",
    )

    autocomplete_fields = (
        "incident",
    )

    readonly_fields = (
        "incident",
        "event_type",
        "payload_pretty",
        "severity_snapshot",
        "created_at",
    )

    date_hierarchy = "created_at"

    ordering = (
        "-created_at",
    )

    def payload_pretty(self, obj):
        return format_html(
            "<pre>{}</pre>",
            json.dumps(
                obj.payload,
                indent=2,
            ),
        )

    payload_pretty.short_description = "Payload"