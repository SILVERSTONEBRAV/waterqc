from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.db.models import (
    Count,
    Sum,
    Avg,
    F,
    ExpressionWrapper,
    FloatField,
)
from django.utils.html import format_html

from .models import (
    MonitoringTime,
    ChemicalCategory,
    ChemicalPump,
    PumpStatus,
    ChemicalTank,
    ChemicalStock,
    CoagulantUsageRecord,
    PHAdjusterUsageRecord,
    DisinfectantUsageRecord,
    FlocculantUsageRecord,
    ChemicalUsageRecord,
    Reservoir,
    ReservoirLevel,
)


# ============================================================
# MIXINS
# ============================================================

class TimestampAdmin(admin.ModelAdmin):
    readonly_fields = (
        "created_at",
        "updated_at",
    )


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================
# MONITORING TIME
# ============================================================

@admin.register(MonitoringTime)
class MonitoringTimeAdmin(admin.ModelAdmin):
    list_display = (
        "time",
        "reservoir_levels",
        "usage_records",
    )

    ordering = ("time",)
    search_fields = ("time",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                reservoir_count=Count(
                    "reservoirlevel"
                )
            )
        )

    def reservoir_levels(self, obj):
        return ReservoirLevel.objects.filter(
            monitoring_time=obj
        ).count()

    reservoir_levels.short_description = "Reservoir Levels"

    def usage_records(self, obj):
        total = (
            CoagulantUsageRecord.objects.filter(
                monitoring_time=obj
            ).count()
            +
            PHAdjusterUsageRecord.objects.filter(
                monitoring_time=obj
            ).count()
            +
            DisinfectantUsageRecord.objects.filter(
                monitoring_time=obj
            ).count()
            +
            FlocculantUsageRecord.objects.filter(
                monitoring_time=obj
            ).count()
        )

        return total

    usage_records.short_description = "Usage Records"


# ============================================================
# CHEMICAL CATEGORY
# ============================================================

@admin.register(ChemicalCategory)
class ChemicalCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "chemical",
        "category_badge",
    )

    list_filter = ("category",)

    search_fields = (
        "chemical__name",
    )

    autocomplete_fields = (
        "chemical",
    )

    def category_badge(self, obj):
        colors = {
            "Coagulant": "#2563eb",
            "PH Adjuster": "#7c3aed",
            "Disinfectant": "#dc2626",
            "Flocculant": "#16a34a",
        }

        return format_html(
            """
            <span style="
                background:{};
                color:white;
                padding:5px 15px;
                border-radius:20px;
                font-weight:600;
            ">
                {}
            </span>
            """,
            colors.get(obj.category, "#64748b"),
            obj.category,
        )

    category_badge.short_description = "Category"


# ============================================================
# CHEMICAL PUMP
# ============================================================

@admin.register(ChemicalPump)
class ChemicalPumpAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phase",
        "category",
        "current_status",
        "status_history",
    )

    search_fields = (
        "name",
        "phase__name",
    )

    list_filter = (
        "category",
        "phase",
    )

    autocomplete_fields = (
        "phase",
    )

    def current_status(self, obj):
        status = (
            obj.statuses
            .order_by("-created_at")
            .first()
        )

        if not status:
            return "-"

        colors = {
            "working": "#16a34a",
            "faulty": "#dc2626",
            "maintenance": "#f59e0b",
            "decommissioned": "#64748b",
        }

        return format_html(
            """
            <span style="
                background:{};
                color:white;
                padding:5px 15px;
                border-radius:20px;
            ">
                {}
            </span>
            """,
            colors.get(status.status),
            status.get_status_display(),
        )

    current_status.short_description = "Current Status"

    def status_history(self, obj):
        return obj.statuses.count()

    status_history.short_description = "History"


# ============================================================
# PUMP STATUS
# ============================================================

@admin.register(PumpStatus)
class PumpStatusAdmin(TimestampAdmin):
    list_display = (
        "pump",
        "treatment_plant",
        "status_badge",
        "updated_by",
        "updated_at",
    )

    search_fields = (
        "pump__name",
        "remarks",
        "treatment_plant__name",
    )

    list_filter = (
        "status",
        "treatment_plant",
        ("updated_at", DateFieldListFilter),
    )

    autocomplete_fields = (
        "pump",
        "treatment_plant",
        "updated_by",
    )

    date_hierarchy = "updated_at"

    def status_badge(self, obj):
        colors = {
            "working": "#16a34a",
            "faulty": "#dc2626",
            "maintenance": "#f59e0b",
            "decommissioned": "#64748b",
        }

        return format_html(
            """
            <span style="
                background:{};
                color:white;
                padding:5px 15px;
                border-radius:20px;
            ">
                {}
            </span>
            """,
            colors.get(obj.status),
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"


# ============================================================
# CHEMICAL TANK
# ============================================================

@admin.register(ChemicalTank)
class ChemicalTankAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phase",
        "category",
        "capacity_liters",
    )

    search_fields = (
        "name",
        "phase__name",
    )

    list_filter = (
        "category",
        "phase",
    )

    autocomplete_fields = (
        "phase",
    )


# ============================================================
# CHEMICAL STOCK
# ============================================================

@admin.register(ChemicalStock)
class ChemicalStockAdmin(TimestampAdmin):
    list_display = (
        "treatment_plant",
        "chemical",
        "stock_bar",
        "quantity_kg",
        "updated_at",
    )

    search_fields = (
        "chemical__name",
        "treatment_plant__name",
    )

    list_filter = (
        "treatment_plant",
        "chemical",
    )

    autocomplete_fields = (
        "treatment_plant",
        "chemical",
    )

    actions = (
        "show_total_stock",
    )

    def stock_bar(self, obj):
        qty = obj.quantity_kg
        percent = min(int(qty), 100)

        color = (
            "#16a34a"
            if qty >= 100
            else "#f59e0b"
            if qty >= 20
            else "#dc2626"
        )

        return format_html(
            """
            <div style="
                width:140px;
                background:#e2e8f0;
                border-radius:8px;
            ">
                <div style="
                    width:{}%;
                    background:{};
                    color:white;
                    text-align:center;
                    border-radius:8px;
                ">
                    {}
                </div>
            </div>
            """,
            percent,
            color,
            round(qty, 2),
        )

    stock_bar.short_description = "Stock"

    @admin.action(description="Calculate total stock")
    def show_total_stock(self, request, queryset):
        total = (
            queryset.aggregate(
                qty=Sum("quantity_kg")
            )["qty"]
            or 0
        )

        self.message_user(
            request,
            f"Total Stock: {round(total,2)} kg",
            messages.SUCCESS,
        )


# ============================================================
# BASE USAGE
# ============================================================

class BaseUsageAdmin(TimestampAdmin):
    list_display = (
        "treatment_plant",
        "phase",
        "chemical",
        "raw_water_flow_rate",
        "actual_dosage",
        "expected_dosage",
        "variance",
        "monitoring_time",
        "date",
    )

    list_filter = (
        "treatment_plant",
        "phase",
        ("date", DateFieldListFilter),
    )

    search_fields = (
        "chemical__name",
        "remarks",
    )

    autocomplete_fields = (
        "treatment_plant",
        "phase",
        "chemical",
        "pump_used",
        "tank_used",
        "monitoring_time",
        "recorded_by",
        "shift_assignment",
    )

    readonly_fields = (
        "expected_dosage",
        "concentration_ppm",
        "created_at",
        "updated_at",
    )

    date_hierarchy = "date"

    def variance(self, obj):
        if not obj.expected_dosage:
            return "-"

        diff = (
            obj.actual_dosage
            - obj.expected_dosage
        )

        color = (
            "#16a34a"
            if diff <= 0
            else "#dc2626"
        )

        return format_html(
            '<span style="color:{};">{:.2f}</span>',
            color,
            diff,
        )

    variance.short_description = "Variance"


@admin.register(CoagulantUsageRecord)
class CoagulantUsageRecordAdmin(BaseUsageAdmin):
    pass


@admin.register(PHAdjusterUsageRecord)
class PHAdjusterUsageRecordAdmin(BaseUsageAdmin):
    pass


@admin.register(DisinfectantUsageRecord)
class DisinfectantUsageRecordAdmin(BaseUsageAdmin):
    list_display = BaseUsageAdmin.list_display + (
        "actual_reading",
        "expected_reading",
    )


@admin.register(FlocculantUsageRecord)
class FlocculantUsageRecordAdmin(BaseUsageAdmin):
    list_display = BaseUsageAdmin.list_display + (
        "batch_number",
        "quantity_used_kg",
    )


# ============================================================
# CHEMICAL USAGE
# ============================================================

@admin.register(ChemicalUsageRecord)
class ChemicalUsageRecordAdmin(TimestampAdmin):
    list_display = (
        "treatment_plant",
        "chemical",
        "quantity_used_kg",
        "date_used",
        "recorded_by",
    )

    search_fields = (
        "chemical__name",
        "remarks",
    )

    list_filter = (
        "treatment_plant",
        "chemical",
        ("date_used", DateFieldListFilter),
    )

    autocomplete_fields = (
        "treatment_plant",
        "chemical",
        "recorded_by",
    )

    date_hierarchy = "date_used"

    actions = (
        "show_total_usage",
    )

    @admin.action(description="Calculate total usage")
    def show_total_usage(self, request, queryset):
        total = (
            queryset.aggregate(
                qty=Sum("quantity_used_kg")
            )["qty"]
            or 0
        )

        self.message_user(
            request,
            f"Total Usage: {round(total,2)} kg",
            messages.SUCCESS,
        )


# ============================================================
# RESERVOIRS
# ============================================================

class ReservoirLevelInline(admin.TabularInline):
    model = ReservoirLevel
    extra = 0
    autocomplete_fields = (
        "monitoring_time",
    )


@admin.register(Reservoir)
class ReservoirAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phase",
        "capacity",
        "latest_level",
        "fill_percentage",
    )

    search_fields = (
        "name",
        "phase__name",
    )

    list_filter = (
        "phase",
    )

    autocomplete_fields = (
        "phase",
    )

    inlines = (
        ReservoirLevelInline,
    )

    def capacity(self, obj):
        return f"{obj.volume_m3()} m³"

    def latest_level(self, obj):
        level = (
            obj.levels
            .order_by(
                "-date",
                "-monitoring_time__time",
            )
            .first()
        )

        if not level:
            return "-"

        return f"{level.level_m} m"

    def fill_percentage(self, obj):
        level = obj.levels.order_by(
            "-date",
            "-monitoring_time__time",
        ).first()

        if not level:
            return "-"

        percent = (
            float(level.level_m)
            / float(obj.depth_m)
        ) * 100

        return f"{round(percent,1)} %"

    fill_percentage.short_description = "Fill %"


# ============================================================
# RESERVOIR LEVEL
# ============================================================

@admin.register(ReservoirLevel)
class ReservoirLevelAdmin(TimestampAdmin):
    list_display = (
        "reservoir",
        "level_m",
        "volume_display",
        "date",
        "monitoring_time",
    )

    search_fields = (
        "reservoir__name",
    )

    list_filter = (
        "reservoir",
        ("date", DateFieldListFilter),
    )

    autocomplete_fields = (
        "reservoir",
        "monitoring_time",
    )

    date_hierarchy = "date"

    def volume_display(self, obj):
        return f"{obj.volume_m3()} m³"

    volume_display.short_description = "Volume"