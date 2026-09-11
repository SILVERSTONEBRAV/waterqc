# duty_house/admin.py

from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Location,
    LocationType,
    DutyHouse,
    DutyHouseStatus,
    DutyHouseUnit,
    UnitStatus,
    DutyHouseOccupancy,
    OccupancyStatus,
    OccupancyTransfer,
)


# ==============================================================================
# BASE ADMIN
# ==============================================================================

class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ==============================================================================
# COMMON BADGES
# ==============================================================================

def render_badge(label, color):
    return format_html(
        """
        <span style="
            background:{};
            color:white;
            padding:4px 12px;
            border-radius:20px;
            font-weight:600;
            font-size:12px;
        ">
            {}
        </span>
        """,
        color,
        label,
    )


def render_progress(value, color):
    value = max(0, min(int(value), 100))

    return format_html(
        """
        <div style="
            width:140px;
            background:#e2e8f0;
            border-radius:10px;
            overflow:hidden;
        ">
            <div style="
                width:{}%;
                background:{};
                color:white;
                text-align:center;
                padding:2px;
                font-weight:600;
            ">
                {}%
            </div>
        </div>
        """,
        value,
        color,
        value,
    )


# ==============================================================================
# LOCATION
# ==============================================================================

class DutyHouseInline(admin.TabularInline):
    model = DutyHouse
    extra = 0
    fields = (
        "house_number",
        "name",
        "status",
        "is_active",
    )
    show_change_link = True


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "plant",
        "location_type_badge",
        "houses_count",
        "active_badge",
    )

    list_filter = (
        "plant",
        "location_type",
        "is_active",
    )

    search_fields = (
        "name",
        "code",
        "plant__name",
    )

    autocomplete_fields = (
        "plant",

    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )

    inlines = (
        DutyHouseInline,
    )

    ordering = (
        "plant",
        "name",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                total_houses=Count("duty_houses")
            )
        )

    def houses_count(self, obj):
        return obj.total_houses

    houses_count.short_description = "Houses"

    def location_type_badge(self, obj):
        colors = {
            LocationType.CAMP: "#2563eb",
            LocationType.BLOCK: "#7c3aed",
            LocationType.WING: "#0f766e",
            LocationType.QUARTERS: "#16a34a",
            LocationType.SECTOR: "#f59e0b",
            LocationType.CUSTOM: "#64748b",
        }

        return render_badge(
            obj.get_location_type_display(),
            colors.get(obj.location_type),
        )

    location_type_badge.short_description = "Type"

    def active_badge(self, obj):
        return render_badge(
            "ACTIVE" if obj.is_active else "INACTIVE",
            "#16a34a" if obj.is_active else "#dc2626",
        )

    active_badge.short_description = "Status"


# ==============================================================================
# UNITS INLINE
# ==============================================================================

class DutyHouseUnitInline(admin.TabularInline):
    model = DutyHouseUnit
    extra = 0
    show_change_link = True
    fields = (
        "unit_number",
        "unit_type",
        "floor",
        "status",
        "max_occupants",
    )


class OccupancyInline(admin.TabularInline):
    model = DutyHouseOccupancy
    extra = 0
    show_change_link = True
    autocomplete_fields = (
        "user",
        "unit",
    )


# ==============================================================================
# DUTY HOUSE
# ==============================================================================

@admin.register(DutyHouse)
class DutyHouseAdmin(admin.ModelAdmin):
    list_display = (
        "house_number",
        "name",
        "plant",
        "location",
        "status_badge",
        "occupancy_badge",
        "maintenance_score_bar",
        "critical_issues_open",
        "is_active",
    )

    list_filter = (
        "plant",
        "status",
        "is_active",
        ("created_at", DateFieldListFilter),
    )

    search_fields = (
        "house_number",
        "name",
        "location__name",
        "plant__name",
    )

    autocomplete_fields = (
        "plant",
        "location",
    )

    readonly_fields = (
        "maintenance_score",
        "critical_issues_open",
        "decommissioned_at",
        "created_at",
        "updated_at",
        "current_occupancy_display",
    )

    inlines = (
        DutyHouseUnitInline,
        OccupancyInline,
    )

    actions = (
        "mark_maintenance",
        "decommission_houses",
        "activate_houses",
    )

    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    ("house_number", "name"),
                    ("plant", "location"),
                    ("floors", "status"),
                )
            },
        ),
        (
            "Geolocation",
            {
                "classes": ("collapse",),
                "fields": (
                    ("gps_lat", "gps_lng"),
                ),
            },
        ),
        (
            "Analytics",
            {
                "fields": (
                    "maintenance_score",
                    "critical_issues_open",
                    "current_occupancy_display",
                    "is_active",
                    "decommissioned_at",
                )
            },
        ),
        (
            "Audit",
            {
                "classes": ("collapse",),
                "fields": (
                    ("created_at", "updated_at"),
                    ("created_by", "updated_by"),
                ),
            },
        ),
    )

    def status_badge(self, obj):
        colors = {
            DutyHouseStatus.ACTIVE: "#16a34a",
            DutyHouseStatus.MAINTENANCE: "#f59e0b",
            DutyHouseStatus.DECOMMISSIONED: "#dc2626",
        }

        return render_badge(
            obj.get_status_display(),
            colors.get(obj.status),
        )

    status_badge.short_description = "Status"

    def maintenance_score_bar(self, obj):
        score = float(obj.maintenance_score)

        color = (
            "#16a34a"
            if score >= 80
            else "#f59e0b"
            if score >= 50
            else "#dc2626"
        )

        return render_progress(score, color)

    maintenance_score_bar.short_description = "Maintenance"

    def occupancy_badge(self, obj):
        occupied = obj.is_occupied()

        return render_badge(
            "Occupied" if occupied else "Vacant",
            "#dc2626" if occupied else "#16a34a",
        )

    occupancy_badge.short_description = "Occupancy"

    def current_occupancy_display(self, obj):
        occ = obj.current_occupancy()

        if not occ:
            return "-"

        return format_html(
            "<strong>{}</strong><br>{}",
            occ.user,
            occ.unit,
        )

    current_occupancy_display.short_description = (
        "Current Occupancy"
    )

    @admin.action(description="Mark selected houses under maintenance")
    def mark_maintenance(self, request, queryset):
        count = queryset.update(
            status=DutyHouseStatus.MAINTENANCE
        )

        self.message_user(
            request,
            f"{count} houses marked under maintenance.",
            messages.SUCCESS,
        )

    @admin.action(description="Decommission selected houses")
    def decommission_houses(self, request, queryset):
        count = 0

        for house in queryset:
            house.decommission()
            count += 1

        self.message_user(
            request,
            f"{count} houses decommissioned.",
            messages.SUCCESS,
        )

    @admin.action(description="Activate selected houses")
    def activate_houses(self, request, queryset):
        count = queryset.update(
            status=DutyHouseStatus.ACTIVE,
            is_active=True,
            decommissioned_at=None,
        )

        self.message_user(
            request,
            f"{count} houses activated.",
            messages.SUCCESS,
        )


# ==============================================================================
# DUTY HOUSE UNIT
# ==============================================================================

class OccupancyHistoryInline(admin.TabularInline):
    model = DutyHouseOccupancy
    extra = 0
    show_change_link = True
    autocomplete_fields = (
        "user",
    )


@admin.register(DutyHouseUnit)
class DutyHouseUnitAdmin(admin.ModelAdmin):
    list_display = (
        "unit_number",
        "duty_house",
        "unit_type",
        "floor",
        "status_badge",
        "occupancy_display",
    )

    list_filter = (
        "unit_type",
        "status",
        "duty_house__plant",
    )

    search_fields = (
        "unit_number",
        "duty_house__house_number",
        "duty_house__name",
    )

    autocomplete_fields = (
        "duty_house",
    )

    readonly_fields = (
        "occupancy_count_display",
        "is_full_display",
        "created_at",
        "updated_at",
    )

    inlines = (
        OccupancyHistoryInline,
    )

    def status_badge(self, obj):
        colors = {
            UnitStatus.VACANT: "#16a34a",
            UnitStatus.OCCUPIED: "#dc2626",
            UnitStatus.MAINTENANCE: "#f59e0b",
        }

        return render_badge(
            obj.get_status_display(),
            colors.get(obj.status),
        )

    status_badge.short_description = "Status"

    def occupancy_display(self, obj):
        return (
            f"{obj.occupancy_count}/"
            f"{obj.max_occupants}"
        )

    occupancy_display.short_description = "Occupancy"

    def occupancy_count_display(self, obj):
        return obj.occupancy_count

    def is_full_display(self, obj):
        return obj.is_full


# ==============================================================================
# OCCUPANCY
# ==============================================================================

@admin.register(DutyHouseOccupancy)
class DutyHouseOccupancyAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "duty_house",
        "unit",
        "status_badge",
        "start_date",
        "end_date",
        "duration_display",
    )

    list_filter = (
        "status",
        "is_current",
        "duty_house__plant",
        ("start_date", DateFieldListFilter),
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "unit__unit_number",
        "duty_house__house_number",
    )

    autocomplete_fields = (
        "duty_house",
        "unit",
        "user",
        "check_in_by",
        "check_out_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    date_hierarchy = "start_date"

    actions = (
        "checkout_selected",
    )

    def status_badge(self, obj):
        colors = {
            OccupancyStatus.ACTIVE: "#16a34a",
            OccupancyStatus.ENDED: "#64748b",
        }

        return render_badge(
            obj.get_status_display(),
            colors.get(obj.status),
        )

    status_badge.short_description = "Status"

    def duration_display(self, obj):
        end = obj.end_date or timezone.now()
        delta = end - obj.start_date
        return f"{delta.days} days"

    duration_display.short_description = "Duration"

    @admin.action(description="Check out selected occupants")
    def checkout_selected(self, request, queryset):
        updated = 0

        for occ in queryset.filter(
            is_current=True
        ):
            occ.is_current = False
            occ.status = OccupancyStatus.ENDED
            occ.end_date = timezone.now()
            occ.check_out_by = request.user
            occ.save()

            updated += 1

        self.message_user(
            request,
            f"{updated} occupants checked out.",
            messages.SUCCESS,
        )


# ==============================================================================
# OCCUPANCY TRANSFER
# ==============================================================================

@admin.register(OccupancyTransfer)
class OccupancyTransferAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "from_unit",
        "to_unit",
        "transferred_at",
        "transferred_by",
    )

    list_filter = (
        "from_unit__duty_house__plant",
        ("transferred_at", DateFieldListFilter),
    )

    search_fields = (
        "user__username",
        "from_unit__unit_number",
        "to_unit__unit_number",
    )

    autocomplete_fields = (
        "from_unit",
        "to_unit",
        "user",
        "transferred_by",
    )

    readonly_fields = (
        "transferred_at",
        "created_at",
        "updated_at",
    )

    date_hierarchy = "transferred_at"

    actions = (
        "execute_transfer",
    )

    @admin.action(description="Execute selected transfers")
    def execute_transfer(self, request, queryset):
        completed = 0

        for transfer in queryset:
            try:
                transfer.execute(request.user)
                completed += 1
            except Exception as e:
                self.message_user(
                    request,
                    str(e),
                    messages.ERROR,
                )

        if completed:
            self.message_user(
                request,
                f"{completed} transfers executed.",
                messages.SUCCESS,
            )