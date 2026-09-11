# maintenance/admin.py

from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    TargetType,
    WorkPriority,
    RequestStatus,
    OrderStatus,
    TaskStatus,
    MaterialTxType,
    SLAStatus,
    WorkRequest,
    WorkOrder,
    WorkTask,
    WorkMaterialUsage,
    WorkLog,
    WorkCost,
    SLARecord,
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
# COMMON MIXINS
# ==============================================================================

class BadgeMixin:
    priority_colors = {
        "low": "#16a34a",
        "medium": "#3b82f6",
        "high": "#f59e0b",
        "critical": "#dc2626",
    }

    request_status_colors = {
        "draft": "#64748b",
        "pending": "#3b82f6",
        "approved": "#16a34a",
        "rejected": "#dc2626",
        "converted": "#7c3aed",
        "closed": "#334155",
    }

    order_status_colors = {
        "queued": "#64748b",
        "assigned": "#3b82f6",
        "in_progress": "#f59e0b",
        "on_hold": "#dc2626",
        "completed": "#16a34a",
        "cancelled": "#334155",
    }

    task_status_colors = {
        "pending": "#64748b",
        "assigned": "#3b82f6",
        "in_progress": "#f59e0b",
        "blocked": "#dc2626",
        "completed": "#16a34a",
        "verified": "#7c3aed",
    }

    sla_colors = {
        "active": "#3b82f6",
        "paused": "#f59e0b",
        "met": "#16a34a",
        "breached": "#dc2626",
    }

    def render_badge(self, text, color):
        return format_html(
            """
            <span style="
                background:{};
                color:white;
                padding:4px 12px;
                border-radius:20px;
                font-weight:600;
                display:inline-block;
                min-width:80px;
                text-align:center;
            ">
                {}
            </span>
            """,
            color,
            text,
        )

    def render_progress(self, value):
        color = (
            "#16a34a"
            if value >= 80
            else "#f59e0b"
            if value >= 40
            else "#dc2626"
        )

        return format_html(
            """
            <div style="width:150px;background:#e5e7eb;border-radius:12px;">
                <div style="
                    width:{}%;
                    background:{};
                    color:white;
                    border-radius:12px;
                    text-align:center;
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
# INLINES
# ==============================================================================

class WorkTaskInline(admin.TabularInline):
    model = WorkTask
    extra = 0
    autocomplete_fields = ("assigned_to",)
    fields = (
        "title",
        "status",
        "assigned_to",
        "started_at",
        "completed_at",
    )


class WorkMaterialUsageInline(admin.TabularInline):
    model = WorkMaterialUsage
    extra = 0
    autocomplete_fields = (
        "inventory_item",
        "issued_by",
    )


class WorkLogInline(admin.TabularInline):
    model = WorkLog
    extra = 0
    readonly_fields = (
        "message",
        "created_by",
        "created_at",
    )

    can_delete = False


# ==============================================================================
# WORK REQUEST
# ==============================================================================

@admin.register(WorkRequest)
class WorkRequestAdmin(BadgeMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "priority_badge",
        "status_badge",
        "target_type",
        "reported_by",
        "is_emergency_badge",
        "created_at",
        "has_sla",
    )

    list_filter = (
        "priority",
        "status",
        "target_type",
        "is_emergency",
        ("created_at", DateFieldListFilter),
    )

    search_fields = (
        "title",
        "description",
        "reported_by__username",
        "duty_house__name",
    )

    autocomplete_fields = (
        "reported_by",
        "approved_by",
        "duty_house",
    )

    readonly_fields = (
        "approved_at",
        "created_at",
        "updated_at",
    )

    date_hierarchy = "created_at"

    actions = (
        "approve_requests",
        "convert_to_orders",
        "mark_closed",
    )

    fieldsets = (
        (
            "Request",
            {
                "fields": (
                    "title",
                    "description",
                    ("priority", "status"),
                    ("target_type", "is_emergency"),
                )
            },
        ),
        (
            "Target",
            {
                "fields": (
                    "duty_house",
                    "equipment_id",
                )
            },
        ),
        (
            "Approval",
            {
                "fields": (
                    "reported_by",
                    "approved_by",
                    "approved_at",
                )
            },
        ),
        (
            "Metadata",
            {
                "classes": ("collapse",),
                "fields": (
                    "metadata",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def priority_badge(self, obj):
        return self.render_badge(
            obj.get_priority_display(),
            self.priority_colors[obj.priority],
        )

    priority_badge.short_description = "Priority"

    def status_badge(self, obj):
        return self.render_badge(
            obj.get_status_display(),
            self.request_status_colors[obj.status],
        )

    status_badge.short_description = "Status"

    def is_emergency_badge(self, obj):
        color = "#dc2626" if obj.is_emergency else "#16a34a"
        label = "YES" if obj.is_emergency else "NO"
        return self.render_badge(label, color)

    is_emergency_badge.short_description = "Emergency"

    def has_sla(self, obj):
        return hasattr(obj, "sla")

    has_sla.boolean = True

    @admin.action(description="Approve selected requests")
    def approve_requests(self, request, queryset):
        count = 0

        for obj in queryset.filter(
            status=RequestStatus.PENDING
        ):
            obj.approve(request.user)
            count += 1

        self.message_user(
            request,
            f"{count} requests approved.",
            messages.SUCCESS,
        )

    @admin.action(description="Convert approved requests to work orders")
    def convert_to_orders(self, request, queryset):
        converted = 0

        for obj in queryset.filter(
            status=RequestStatus.APPROVED
        ):
            obj.convert_to_order()
            converted += 1

        self.message_user(
            request,
            f"{converted} work orders created.",
            messages.SUCCESS,
        )

    @admin.action(description="Close selected requests")
    def mark_closed(self, request, queryset):
        queryset.update(status=RequestStatus.CLOSED)


# ==============================================================================
# WORK ORDER
# ==============================================================================

@admin.register(WorkOrder)
class WorkOrderAdmin(BadgeMixin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "request",
        "priority_badge",
        "status_badge",
        "assigned_to",
        "supervisor",
        "progress_bar",
        "tasks_count",
        "materials_count",
    )

    list_filter = (
        "priority",
        "status",
        ("created_at", DateFieldListFilter),
        ("completed_at", DateFieldListFilter),
    )

    search_fields = (
        "request__title",
        "assigned_to__username",
        "supervisor__username",
    )

    autocomplete_fields = (
        "request",
        "assigned_to",
        "supervisor",
        "duty_house",
    )

    readonly_fields = (
        "progress",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )

    inlines = (
        WorkTaskInline,
        WorkMaterialUsageInline,
        WorkLogInline,
    )

    date_hierarchy = "created_at"

    actions = (
        "start_orders",
        "complete_orders",
        "assign_to_me",
    )

    fieldsets = (
        (
            "Order",
            {
                "fields": (
                    "request",
                    ("priority", "status"),
                    ("assigned_to", "supervisor"),
                    "duty_house",
                )
            }
        ),
        (
            "Execution",
            {
                "fields": (
                    "progress",
                    "started_at",
                    "completed_at",
                )
            },
        ),
        (
            "Metadata",
            {
                "classes": ("collapse",),
                "fields": (
                    "metadata",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                total_tasks=Count("tasks"),
                total_materials=Count("materials"),
            )
        )

    def priority_badge(self, obj):
        return self.render_badge(
            obj.get_priority_display(),
            self.priority_colors[obj.priority],
        )

    def status_badge(self, obj):
        return self.render_badge(
            obj.get_status_display(),
            self.order_status_colors[obj.status],
        )

    def progress_bar(self, obj):
        return self.render_progress(obj.progress)

    progress_bar.short_description = "Progress"

    def tasks_count(self, obj):
        return obj.total_tasks

    def materials_count(self, obj):
        return obj.total_materials

    @admin.action(description="Start selected orders")
    def start_orders(self, request, queryset):
        count = 0

        for order in queryset:
            try:
                order.start()
                count += 1
            except Exception:
                pass

        self.message_user(
            request,
            f"{count} orders started.",
            messages.SUCCESS,
        )

    @admin.action(description="Complete selected orders")
    def complete_orders(self, request, queryset):
        completed = 0

        for order in queryset:
            try:
                order.complete()
                completed += 1
            except Exception:
                pass

        self.message_user(
            request,
            f"{completed} orders completed.",
            messages.SUCCESS,
        )

    @admin.action(description="Assign selected orders to myself")
    def assign_to_me(self, request, queryset):
        queryset.update(
            assigned_to=request.user,
            status=OrderStatus.ASSIGNED,
        )


# ==============================================================================
# WORK TASK
# ==============================================================================

@admin.register(WorkTask)
class WorkTaskAdmin(BadgeMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "order",
        "status_badge",
        "assigned_to",
        "started_at",
        "completed_at",
    )

    list_filter = (
        "status",
        ("created_at", DateFieldListFilter),
    )

    search_fields = (
        "title",
        "description",
    )

    autocomplete_fields = (
        "order",
        "assigned_to",
    )

    actions = (
        "start_tasks",
        "complete_tasks",
    )

    def status_badge(self, obj):
        return self.render_badge(
            obj.get_status_display(),
            self.task_status_colors[obj.status],
        )

    @admin.action(description="Start selected tasks")
    def start_tasks(self, request, queryset):
        for task in queryset:
            task.start()

    @admin.action(description="Complete selected tasks")
    def complete_tasks(self, request, queryset):
        for task in queryset:
            task.complete()


# ==============================================================================
# MATERIAL USAGE
# ==============================================================================

@admin.register(WorkMaterialUsage)
class WorkMaterialUsageAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "inventory_item",
        "quantity",
        "transaction_type",
        "issued_by",
        "applied",
    )

    list_filter = (
        "transaction_type",
        "applied",
    )

    search_fields = (
        "inventory_item__item_name",
    )

    autocomplete_fields = (
        "order",
        "inventory_item",
        "issued_by",
    )

    actions = (
        "apply_transactions",
    )

    @admin.action(description="Apply selected transactions")
    def apply_transactions(self, request, queryset):
        count = 0

        for tx in queryset.filter(applied=False):
            tx.apply()
            count += 1

        self.message_user(
            request,
            f"{count} transactions applied.",
            messages.SUCCESS,
        )


# ==============================================================================
# WORK LOG
# ==============================================================================

@admin.register(WorkLog)
class WorkLogAdmin(ReadOnlyAdmin):
    list_display = (
        "order",
        "message",
        "created_by",
        "created_at",
    )

    search_fields = (
        "message",
    )

    autocomplete_fields = (
        "order",
        "created_by",
    )

    date_hierarchy = "created_at"


# ==============================================================================
# COSTS
# ==============================================================================

@admin.register(WorkCost)
class WorkCostAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "labor_cost",
        "materials_cost",
        "total_cost",
    )

    autocomplete_fields = ("order",)

    readonly_fields = (
        "total_cost",
    )

    def total_cost(self, obj):
        return f"{obj.total:,.2f}"

    total_cost.short_description = "Total Cost"


# ==============================================================================
# SLA
# ==============================================================================

@admin.register(SLARecord)
class SLARecordAdmin(BadgeMixin, admin.ModelAdmin):
    list_display = (
        "request",
        "status_badge",
        "response_due",
        "resolution_due",
        "response_remaining",
        "resolution_remaining",
    )

    list_filter = (
        "status",
        ("response_due", DateFieldListFilter),
        ("resolution_due", DateFieldListFilter),
    )

    search_fields = (
        "request__title",
    )

    autocomplete_fields = (
        "request",
    )

    readonly_fields = (
        "responded_at",
        "resolved_at",
    )

    date_hierarchy = "response_due"

    def status_badge(self, obj):
        return self.render_badge(
            obj.get_status_display(),
            self.sla_colors[obj.status],
        )

    def response_remaining(self, obj):
        delta = obj.response_due - timezone.now()
        return str(delta).split(".")[0]

    def resolution_remaining(self, obj):
        delta = obj.resolution_due - timezone.now()
        return str(delta).split(".")[0]