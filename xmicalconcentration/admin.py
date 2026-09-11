# xmicalconcentration/admin.py

from decimal import Decimal

from django.contrib import admin, messages
from django.db.models import Avg, Max, Min
from django.utils.html import format_html
from django.utils import timezone

from .models import XmicalConcentration


# ============================================================
# Actions
# ============================================================

@admin.action(description="Mark selected measurements as reviewed")
def mark_reviewed(modeladmin, request, queryset):
    updated = queryset.update(
        comments="Reviewed by administrator."
    )
    messages.success(
        request,
        f"{updated} measurements marked as reviewed."
    )


# ============================================================
# Admin
# ============================================================

@admin.register(XmicalConcentration)
class XmicalConcentrationAdmin(admin.ModelAdmin):
    """
    Enterprise Chemical Concentration Admin
    """

    actions = [mark_reviewed]

    save_on_top = True

    date_hierarchy = "measurement_date"

    list_per_page = 50

    ordering = (
        "-measurement_date",
        "chemical_name",
    )

    list_select_related = (
        "treatment_plant",
        "phase",
        "chemical",
        "tank",
        "measured_by",
        "created_by",
        "updated_by",
    )

    search_fields = (
        "id",
        "chemical_name",
        "chemical__name",
        "tank__name",
        "treatment_plant__name",
        "phase__name",
        "comments",
        "formula_used",
        "measured_by__username",
        "created_by__username",
    )

    list_filter = (
        "treatment_plant",
        "phase",
        "chemical",
        "tank",
        "measurement_date",
        "created_at",
        "measured_by",
    )

    autocomplete_fields = (
        "treatment_plant",
        "phase",
        "chemical",
        "tank",
        "measured_by",
        "created_by",
        "updated_by",
    )

    readonly_fields = (
        "id",
        "chemical_name",
        "concentration_mg_per_l",
        "formula_used",
        "created_at",
        "updated_at",
        "concentration_indicator",
        "formula_preview",
        "statistics_panel",
    )

    fieldsets = (
        (
            "Measurement Information",
            {
                "fields": (
                    "id",
                    "treatment_plant",
                    "phase",
                    "tank",
                    "chemical",
                    "chemical_name",
                    "measurement_date",
                    "measured_by",
                )
            },
        ),
        (
            "Hydrometer Data",
            {
                "fields": (
                    "hydrometer_reading",
                    "concentration_mg_per_l",
                    "concentration_indicator",
                )
            },
        ),
        (
            "Formula Information",
            {
                "classes": ("collapse",),
                "fields": (
                    "formula_used",
                    "formula_preview",
                ),
            },
        ),
        (
            "Notes",
            {
                "fields": (
                    "comments",
                )
            },
        ),
        (
            "Audit Information",
            {
                "classes": ("collapse",),
                "fields": (
                    "created_by",
                    "updated_by",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
        (
            "Analytics",
            {
                "classes": ("collapse",),
                "fields": (
                    "statistics_panel",
                ),
            },
        ),
    )

    # =====================================================
    # Query Optimisation
    # =====================================================

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return (
            qs.select_related(
                "treatment_plant",
                "phase",
                "chemical",
                "tank",
                "measured_by",
                "created_by",
                "updated_by",
            )
        )

    # =====================================================
    # List Display
    # =====================================================

    list_display = (
        "measurement_date",
        "treatment_plant",
        "phase",
        "chemical_name",
        "tank",
        "hydrometer_reading",
        "colored_concentration",
        "measured_by",
        "is_recent_badge",
    )

    # =====================================================
    # Display Helpers
    # =====================================================

    @admin.display(
        description="Concentration",
        ordering="concentration_mg_per_l",
    )
    def colored_concentration(self, obj):
        value = Decimal(obj.concentration_mg_per_l)

        if value >= 100:
            color = "#dc2626"
        elif value >= 50:
            color = "#ea580c"
        elif value >= 20:
            color = "#16a34a"
        else:
            color = "#2563eb"

        return format_html(
            """
            <span style="
                background:{};
                color:white;
                padding:4px 10px;
                border-radius:20px;
                font-weight:600;
            ">
                {} mg/L
            </span>
            """,
            color,
            value,
        )

    @admin.display(
        boolean=True,
        description="Recent",
    )
    def is_recent_badge(self, obj):
        return obj.is_recent

    # =====================================================
    # Readonly Panels
    # =====================================================

    def concentration_indicator(self, obj):
        if not obj.pk:
            return "-"

        value = float(obj.concentration_mg_per_l)

        width = min(value, 100)

        return format_html(
            """
            <div style="
                width:300px;
                border:1px solid #ddd;
                border-radius:8px;
                overflow:hidden;
            ">
                <div style="
                    width:{}%;
                    height:20px;
                    background:#16a34a;
                "></div>
            </div>
            <small>{} mg/L</small>
            """,
            width,
            value,
        )

    concentration_indicator.short_description = "Concentration Level"

    def formula_preview(self, obj):
        if not obj.pk:
            return "-"

        return format_html(
            """
            <pre style="
                background:#f8fafc;
                padding:15px;
                border-radius:8px;
                white-space:pre-wrap;
            ">
{}
            </pre>
            """,
            obj.formula_used,
        )

    formula_preview.short_description = "Formula Snapshot"

    def statistics_panel(self, obj):
        if not obj.pk:
            return "-"

        qs = XmicalConcentration.objects.filter(
            chemical=obj.chemical
        )

        stats = qs.aggregate(
            avg=Avg("concentration_mg_per_l"),
            min=Min("concentration_mg_per_l"),
            max=Max("concentration_mg_per_l"),
        )

        return format_html(
            """
            <table style="
                width:100%;
                border-collapse:collapse;
            ">
                <tr>
                    <th style="padding:8px;">Average</th>
                    <th style="padding:8px;">Minimum</th>
                    <th style="padding:8px;">Maximum</th>
                    <th style="padding:8px;">Samples</th>
                </tr>
                <tr>
                    <td style="padding:8px;">{}</td>
                    <td style="padding:8px;">{}</td>
                    <td style="padding:8px;">{}</td>
                    <td style="padding:8px;">{}</td>
                </tr>
            </table>
            """,
            round(stats["avg"] or 0, 3),
            round(stats["min"] or 0, 3),
            round(stats["max"] or 0, 3),
            qs.count(),
        )

    statistics_panel.short_description = "Chemical Statistics"

    # =====================================================
    # Save Hooks
    # =====================================================

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user

        obj.updated_by = request.user

        super().save_model(
            request,
            obj,
            form,
            change,
        )

    # =====================================================
    # Dashboard Metrics
    # =====================================================

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        qs = self.get_queryset(request)

        extra_context["total_measurements"] = qs.count()

        extra_context["today_measurements"] = qs.filter(
            measurement_date__date=timezone.now().date()
        ).count()

        extra_context["avg_concentration"] = qs.aggregate(
            avg=Avg("concentration_mg_per_l")
        )["avg"]

        return super().changelist_view(
            request,
            extra_context=extra_context,
        )