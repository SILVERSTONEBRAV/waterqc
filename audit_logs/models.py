# audit_logs/models.py

import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

CustomUser = get_user_model()


# =========================================================
# BASE MIXIN (IMMUTABLE AUDIT CORE)
# =========================================================

class AuditBaseModel(models.Model):
    """
    Shared immutable audit foundation.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_records"
    )

    request_id = models.UUIDField(
        default=uuid.uuid4,
        db_index=True,
        editable=False
    )

    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        db_index=True
    )

    device = models.CharField(
        max_length=50,
        blank=True,
        db_index=True
    )

    user_agent = models.TextField(
        blank=True
    )

    location = models.CharField(
        max_length=255,
        blank=True,
        db_index=True
    )

    class Meta:
        abstract = True


# =========================================================
# PRIORITY / STATUS ENUMS
# =========================================================

class AuditStatus(models.TextChoices):
    SUCCESS = "success", _("Success")
    FAILURE = "failure", _("Failure")
    PENDING = "pending", _("Pending")


class AuditPriority(models.IntegerChoices):
    LOW = 0, "Low"
    NORMAL = 1, "Normal"
    HIGH = 2, "High"
    CRITICAL = 3, "Critical"


class ActivityType(models.TextChoices):
    LOGIN = "login", "Login"
    LOGOUT = "logout", "Logout"
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    READ = "read", "Read"
    SYSTEM = "system", "System"
    OTHER = "other", "Other"


# =========================================================
# AUDIT LOG ENTRY (PRIMARY EVENT LOG)
# =========================================================

class AuditLogEntry(AuditBaseModel):
    """
    Primary immutable audit event.
    Represents WHAT happened.
    """

    action = models.CharField(
        max_length=255,
        db_index=True
    )

    result_status = models.CharField(
        max_length=20,
        choices=AuditStatus.choices,
        default=AuditStatus.PENDING,
        db_index=True
    )

    priority = models.IntegerField(
        choices=AuditPriority.choices,
        default=AuditPriority.NORMAL,
        db_index=True
    )

    description = models.TextField(
        blank=True
    )

    additional_data = models.JSONField(
        default=dict,
        blank=True
    )

    duration = models.FloatField(
        null=True,
        blank=True,
        help_text="Request duration in seconds"
    )

    http_method = models.CharField(
        max_length=10,
        blank=True
    )

    path = models.CharField(
        max_length=500,
        blank=True,
        db_index=True
    )

    status_code = models.IntegerField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["action"]),
            models.Index(fields=["result_status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["request_id"]),
        ]

    def __str__(self):
        user = getattr(self.user, "username", "system")
        return f"[{self.result_status}] {user} → {self.action}"


# =========================================================
# USER ACTIVITY (OPTIONAL EXTENSION / TELEMETRY LAYER)
# =========================================================

class UserActivity(AuditBaseModel):
    """
    Secondary telemetry layer.
    Represents HOW the action was performed.
    """

    audit_entry = models.ForeignKey(
        AuditLogEntry,
        on_delete=models.CASCADE,
        related_name="activities"
    )

    activity_type = models.CharField(
        max_length=50,
        choices=ActivityType.choices,
        default=ActivityType.OTHER,
        db_index=True
    )

    successful_attempt = models.BooleanField(
        default=False,
        db_index=True
    )

    duration = models.DurationField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["audit_entry"]),
            models.Index(fields=["activity_type"]),
        ]

    def __str__(self):
        user = getattr(self.user, "username", "system")
        return f"{user} → {self.activity_type}"