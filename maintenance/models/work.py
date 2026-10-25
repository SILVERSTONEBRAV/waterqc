# maintenance/models/work.py
import uuid
from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .audit import AuditModel


class TargetType(models.TextChoices):
    DUTY_HOUSE = "duty_house", "Duty House"
    EQUIPMENT = "equipment", "Equipment"


class WorkPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class RequestStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CONVERTED = "converted", "Converted"
    CLOSED = "closed", "Closed"


class OrderStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    ASSIGNED = "assigned", "Assigned"
    IN_PROGRESS = "in_progress", "In Progress"
    ON_HOLD = "on_hold", "On Hold"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class TaskStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ASSIGNED = "assigned", "Assigned"
    IN_PROGRESS = "in_progress", "In Progress"
    BLOCKED = "blocked", "Blocked"
    COMPLETED = "completed", "Completed"
    VERIFIED = "verified", "Verified"


class MaterialTxType(models.TextChoices):
    RESERVE = "reserve", "Reserve"
    ISSUE = "issue", "Issue"
    RELEASE = "release", "Release"


class SLAStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    MET = "met", "Met"
    BREACHED = "breached", "Breached"


# =========================================================
# WORK REQUEST
# =========================================================

class WorkRequest(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    title = models.CharField(max_length=255)

    description = models.TextField()

    priority = models.CharField(
        max_length=20,
        choices=WorkPriority.choices,
        default=WorkPriority.MEDIUM,
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=RequestStatus.choices,
        default=RequestStatus.DRAFT,
        db_index=True,
    )

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_requests",
    )

    target_type = models.CharField(
        max_length=20,
        choices=TargetType.choices,
        db_index=True,
    )

    duty_house = models.ForeignKey(
        "duty_house.DutyHouse",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="maintenance_requests",
    )

    equipment_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    is_emergency = models.BooleanField(
        default=False,
        db_index=True,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_work_requests",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["target_type"]),
            models.Index(fields=["reported_by"]),
            models.Index(fields=["is_emergency"]),
        ]

    def clean(self):
        super().clean()

        if (
            self.target_type == TargetType.DUTY_HOUSE
            and not self.duty_house
        ):
            raise ValidationError(
                {"duty_house": "Duty house is required."}
            )

        if (
            self.target_type == TargetType.EQUIPMENT
            and not self.equipment_id
        ):
            raise ValidationError(
                {"equipment_id": "Equipment is required."}
            )

    def approve(self, user):
        if self.status != RequestStatus.PENDING:
            raise ValidationError(
                "Only pending requests may be approved."
            )

        self.status = RequestStatus.APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "approved_by",
                "approved_at",
            ]
        )

    @transaction.atomic
    def convert_to_order(self):
        if self.status != RequestStatus.APPROVED:
            raise ValidationError(
                "Request must be approved."
            )

        if hasattr(self, "order"):
            return self.order

        order = WorkOrder.objects.create(
            request=self,
            priority=self.priority,
            duty_house=self.duty_house,
        )

        self.status = RequestStatus.CONVERTED
        self.save(update_fields=["status"])

        return order

    def __str__(self):
        return self.title


# =========================================================
# WORK ORDER
# =========================================================

class WorkOrder(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    request = models.OneToOneField(
        "maintenance.WorkRequest",
        on_delete=models.CASCADE,
        related_name="order",
    )

    duty_house = models.ForeignKey(
        "duty_house.DutyHouse",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="work_orders",
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_work_orders",
    )

    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supervised_work_orders",
    )

    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.QUEUED,
        db_index=True,
    )

    priority = models.CharField(
        max_length=20,
        choices=WorkPriority.choices,
        db_index=True,
    )

    progress = models.PositiveIntegerField(
        default=0,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["assigned_to"]),
            models.Index(fields=["supervisor"]),
        ]

    def assign(self, user):
        self.assigned_to = user
        self.status = OrderStatus.ASSIGNED
        self.save(update_fields=["assigned_to", "status"])

    def start(self):
        if self.status not in {
            OrderStatus.QUEUED,
            OrderStatus.ASSIGNED,
        }:
            raise ValidationError(
                "Invalid state transition."
            )

        self.status = OrderStatus.IN_PROGRESS
        self.started_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "started_at",
            ]
        )

    def update_progress(self):
        total = self.tasks.count()

        if total == 0:
            return

        completed = self.tasks.filter(
            status__in=[
                TaskStatus.COMPLETED,
                TaskStatus.VERIFIED,
            ]
        ).count()

        self.progress = int(
            (completed / total) * 100
        )

        self.save(update_fields=["progress"])

    def complete(self):
        if self.tasks.exclude(
            status__in=[
                TaskStatus.COMPLETED,
                TaskStatus.VERIFIED,
            ]
        ).exists():
            raise ValidationError(
                "All tasks must be completed."
            )

        self.status = OrderStatus.COMPLETED
        self.progress = 100
        self.completed_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "progress",
                "completed_at",
            ]
        )

    def __str__(self):
        return f"WO-{self.pk}"


# =========================================================
# WORK TASK
# =========================================================

class WorkTask(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    order = models.ForeignKey(
        "maintenance.WorkOrder",
        on_delete=models.CASCADE,
        related_name="tasks",
    )

    title = models.CharField(max_length=255)

    description = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.PENDING,
        db_index=True,
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_tasks",
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    def start(self):
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "started_at",
            ]
        )

    def complete(self):
        self.status = TaskStatus.COMPLETED
        self.completed_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "completed_at",
            ]
        )

        self.order.update_progress()

    def __str__(self):
        return self.title


# =========================================================
# MATERIAL USAGE
# =========================================================

class WorkMaterialUsage(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    order = models.ForeignKey(
        "maintenance.WorkOrder",
        on_delete=models.CASCADE,
        related_name="materials",
    )

    inventory_item = models.ForeignKey(
        "inventory.InventoryItem",
        on_delete=models.PROTECT,
        related_name="maintenance_usage",
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=MaterialTxType.choices,
    )

    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="issued_material_transactions",
    )

    applied = models.BooleanField(
        default=False,
        db_index=True,
    )

    @transaction.atomic
    def apply(self):
        if self.applied:
            return

        ledger = self.inventory_item.stock

        if self.transaction_type == MaterialTxType.RESERVE:
            ledger.reserve(self.quantity)

        elif self.transaction_type == MaterialTxType.ISSUE:
            ledger.issue(self.quantity)

        elif self.transaction_type == MaterialTxType.RELEASE:
            ledger.release_reservation(self.quantity)

        self.applied = True
        self.save(update_fields=["applied"])


# =========================================================
# WORK LOG
# =========================================================

class WorkLog(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    order = models.ForeignKey(
        "maintenance.WorkOrder",
        on_delete=models.CASCADE,
        related_name="logs",
    )

    message = models.TextField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_logs",
    )

    def __str__(self):
        return self.message[:80]


# =========================================================
# COST ENGINE
# =========================================================

class WorkCost(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    order = models.OneToOneField(
        "maintenance.WorkOrder",
        on_delete=models.CASCADE,
        related_name="cost",
    )

    labor_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    materials_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    @property
    def total(self):
        return self.labor_cost + self.materials_cost


# =========================================================
# SLA ENGINE
# =========================================================

class SLARecord(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    request = models.OneToOneField(
        "maintenance.WorkRequest",
        on_delete=models.CASCADE,
        related_name="sla",
    )

    status = models.CharField(
        max_length=20,
        choices=SLAStatus.choices,
        default=SLAStatus.ACTIVE,
    )

    response_due = models.DateTimeField()
    resolution_due = models.DateTimeField()

    responded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    breach_reason = models.TextField(
        null=True,
        blank=True,
    )

    def mark_responded(self):
        self.responded_at = timezone.now()
        self.save(update_fields=["responded_at"])

    def mark_resolved(self):
        self.resolved_at = timezone.now()

        if self.resolved_at > self.resolution_due:
            self.status = SLAStatus.BREACHED
            self.breach_reason = "Late resolution"
        else:
            self.status = SLAStatus.MET

        self.save(
            update_fields=[
                "resolved_at",
                "status",
                "breach_reason",
            ]
        )


# =========================================================
# AUTOMATIC SLA CREATION
# =========================================================

@receiver(post_save, sender=WorkRequest)
def create_sla(sender, instance, created, **kwargs):
    if not created:
        return

    if hasattr(instance, "sla"):
        return

    response_hours = 4
    resolution_hours = 24

    if instance.priority == WorkPriority.CRITICAL:
        response_hours = 1
        resolution_hours = 4

    elif instance.priority == WorkPriority.HIGH:
        response_hours = 2
        resolution_hours = 12

    SLARecord.objects.create(
        request=instance,
        response_due=(
            instance.created_at
            + timedelta(hours=response_hours)
        ),
        resolution_due=(
            instance.created_at
            + timedelta(hours=resolution_hours)
        ),
    )