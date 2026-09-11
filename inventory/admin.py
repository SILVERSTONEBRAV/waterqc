# inventory/admin.py

from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.db.models import Count, Sum, F, DecimalField
from django.db.models.functions import Coalesce
from django.utils.html import format_html
from django.utils import timezone

from .models import (
    Status,
    Category,
    Supplier,
    ItemType,
    StockLedger,
    AlertConfig,
    InventoryItem,
    InventoryTransaction,
    WorkMaterialReservation,
    LaboratoryReagent,
    Equipment,
    AuditLog,
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

class InventoryTransactionInline(admin.TabularInline):
    model = InventoryTransaction
    extra = 0
    fields = (
        "transaction_type",
        "quantity",
        "performed_by",
        "created_at",
    )
    readonly_fields = ("created_at",)
    autocomplete_fields = ("performed_by",)
    show_change_link = True


class StockLedgerInline(admin.StackedInline):
    model = StockLedger
    extra = 0
    can_delete = False
    readonly_fields = (
        "available",
        "reserved",
        "issued",
        "updated_at",
    )


# =============================================================================
# STATUS
# =============================================================================

@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "description",
    )
    search_fields = (
        "name",
        "description",
    )
    ordering = ("name",)


# =============================================================================
# CATEGORY
# =============================================================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "item_count",
        "equipment_count",
    )

    search_fields = (
        "name",
        "description",
    )

    ordering = ("name",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                total_items=Count("items", distinct=True),
                total_equipment=Count("equipment", distinct=True),
            )
        )

    def item_count(self, obj):
        return obj.total_items

    def equipment_count(self, obj):
        return obj.total_equipment


# =============================================================================
# SUPPLIER
# =============================================================================

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phone",
        "email",
        "inventory_count",
    )

    search_fields = (
        "name",
        "phone",
        "email",
        "address",
    )

    ordering = ("name",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                total_inventory=Count("inventoryitem")
            )
        )

    def inventory_count(self, obj):
        return obj.total_inventory


# =============================================================================
# ITEM TYPE
# =============================================================================

@admin.register(ItemType)
class ItemTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "item_count",
    )

    search_fields = ("name",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                total_items=Count("items")
            )
        )

    def item_count(self, obj):
        return obj.total_items


# =============================================================================
# STOCK LEDGER
# =============================================================================

@admin.register(StockLedger)
class StockLedgerAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "available",
        "reserved",
        "issued",
        "total_stock",
        "updated_at",
    )

    list_filter = (
        "updated_at",
    )

    search_fields = (
        "item__name",
        "item__category__name",
    )

    autocomplete_fields = ("item",)

    readonly_fields = (
        "updated_at",
        "total_stock",
    )

    def total_stock(self, obj):
        return obj.available + obj.reserved + obj.issued


# =============================================================================
# ALERT CONFIG
# =============================================================================

@admin.register(AlertConfig)
class AlertConfigAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "alert_type",
        "section",
        "category",
        "threshold_days",
        "min_quantity",
        "active_badge",
    )

    list_filter = (
        "alert_type",
        "active",
        "section",
        "category",
    )

    search_fields = (
        "name",
        "section__name",
        "category__name",
    )

    autocomplete_fields = (
        "section",
        "category",
        "users_to_notify",
    )

    filter_horizontal = (
        "users_to_notify",
    )

    list_editable = (
        "threshold_days",
        "min_quantity",
    )

    def active_badge(self, obj):
        color = "#16a34a" if obj.active else "#dc2626"
        label = "ACTIVE" if obj.active else "DISABLED"

        return format_html(
            '<span style="background:{};color:white;padding:4px 10px;border-radius:20px;">{}</span>',
            color,
            label,
        )

    active_badge.short_description = "Status"


# =============================================================================
# INVENTORY ITEM
# =============================================================================

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "item_type",
        "category",
        "section",
        "supplier",
        "quantity",
        "available_stock",
        "reserved_stock",
        "issued_stock",
        "locked_badge",
    )

    list_filter = (
        "item_type",
        "category",
        "section",
        "supplier",
        "is_locked",
    )

    search_fields = (
        "name",
        "category__name",
        "supplier__name",
        "section__name",
    )

    autocomplete_fields = (
        "item_type",
        "category",
        "section",
        "supplier",
    )

    inlines = (
        StockLedgerInline,
        InventoryTransactionInline,
    )

    actions = (
        "lock_inventory",
        "unlock_inventory",
    )

    def available_stock(self, obj):
        return obj.stock.available

    def reserved_stock(self, obj):
        return obj.stock.reserved

    def issued_stock(self, obj):
        return obj.stock.issued

    def locked_badge(self, obj):
        color = "#dc2626" if obj.is_locked else "#16a34a"
        label = "LOCKED" if obj.is_locked else "OPEN"

        return format_html(
            '<span style="background:{};color:white;padding:4px 10px;border-radius:20px;">{}</span>',
            color,
            label,
        )

    @admin.action(description="Lock selected inventory")
    def lock_inventory(self, request, queryset):
        queryset.update(is_locked=True)

    @admin.action(description="Unlock selected inventory")
    def unlock_inventory(self, request, queryset):
        queryset.update(is_locked=False)


# =============================================================================
# INVENTORY TRANSACTION
# =============================================================================

@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "transaction_badge",
        "quantity",
        "performed_by",
        "created_at",
    )

    list_filter = (
        "transaction_type",
        ("created_at", DateFieldListFilter),
    )

    search_fields = (
        "item__name",
        "performed_by__username",
        "notes",
    )

    autocomplete_fields = (
        "item",
        "performed_by",
    )

    date_hierarchy = "created_at"

    readonly_fields = (
        "created_at",
    )

    def transaction_badge(self, obj):
        colors = {
            "addition": "#16a34a",
            "removal": "#dc2626",
            "adjustment": "#2563eb",
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
            colors.get(obj.transaction_type),
            obj.get_transaction_type_display(),
        )

    transaction_badge.short_description = "Type"


# =============================================================================
# WORK MATERIAL RESERVATIONS
# =============================================================================

@admin.register(WorkMaterialReservation)
class WorkMaterialReservationAdmin(admin.ModelAdmin):
    list_display = (
        "work_order_id",
        "inventory_item",
        "quantity",
        "status_badge",
        "created_at",
    )

    list_filter = (
        "status",
        ("created_at", DateFieldListFilter),
    )

    search_fields = (
        "work_order_id",
        "inventory_item__name",
    )

    autocomplete_fields = ("inventory_item",)

    readonly_fields = ("created_at",)

    actions = (
        "mark_issued",
        "mark_released",
    )

    def status_badge(self, obj):
        colors = {
            "reserved": "#f59e0b",
            "issued": "#16a34a",
            "released": "#2563eb",
        }

        return format_html(
            '<span style="background:{};color:white;padding:4px 10px;border-radius:20px;">{}</span>',
            colors.get(obj.status),
            obj.get_status_display(),
        )

    @admin.action(description="Issue selected reservations")
    def mark_issued(self, request, queryset):
        for obj in queryset:
            obj.issue()

    @admin.action(description="Release selected reservations")
    def mark_released(self, request, queryset):
        for obj in queryset:
            obj.release()


# =============================================================================
# LABORATORY REAGENTS
# =============================================================================

@admin.register(LaboratoryReagent)
class LaboratoryReagentAdmin(admin.ModelAdmin):
    list_display = (
        "rname",
        "category",
        "quantity",
    )

    list_filter = (
        "category",
    )

    search_fields = (
        "rname",
        "category__name",
    )

    autocomplete_fields = (
        "category",
    )


# =============================================================================
# EQUIPMENT
# =============================================================================

@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "section",
        "serial_number",
        "maintenance_due",
        "calibration_due",
    )

    list_filter = (
        "category",
        "section",
    )

    search_fields = (
        "name",
        "serial_number",
    )

    autocomplete_fields = (
        "category",
        "section",
    )

    date_hierarchy = "next_maintenance_date"

    def maintenance_due(self, obj):
        if not obj.next_maintenance_date:
            return "-"

        days = (obj.next_maintenance_date - timezone.now().date()).days

        if days < 0:
            return format_html(
                '<span style="color:red;font-weight:bold;">OVERDUE</span>'
            )

        return f"{days} days"

    def calibration_due(self, obj):
        if not obj.next_calibration_date:
            return "-"

        days = (obj.next_calibration_date - timezone.now().date()).days

        if days < 0:
            return format_html(
                '<span style="color:red;font-weight:bold;">OVERDUE</span>'
            )

        return f"{days} days"


# =============================================================================
# AUDIT LOG
# =============================================================================

@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyAdmin):
    list_display = (
        "timestamp",
        "action",
        "content_type",
        "object_id",
        "user",
    )

    list_filter = (
        "action",
        "content_type",
        ("timestamp", DateFieldListFilter),
    )

    search_fields = (
        "action",
        "notes",
        "object_id",
        "user__username",
    )

    readonly_fields = (
        "content_type",
        "object_id",
        "content_object",
        "action",
        "user",
        "notes",
        "timestamp",
    )

    ordering = ("-timestamp",)