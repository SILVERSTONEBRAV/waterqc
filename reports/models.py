from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid


# =========================================================
# 🧩 ENUMS
# =========================================================

class ReportStatus(models.TextChoices):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReportFormat(models.TextChoices):
    JSON = "JSON"
    PDF = "PDF"
    EXCEL = "EXCEL"


class AnalysisType(models.TextChoices):
    BASIC = "BASIC"
    STATISTICAL = "STATISTICAL"
    PREDICTIVE = "PREDICTIVE"
    ADVANCED = "ADVANCED"
    AI_MODEL = "AI_MODEL"


# =========================================================
# 🧱 CORE MIXINS
# =========================================================

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditModel(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="%(class)s_created"
    )

    class Meta:
        abstract = True


class StatusModel(models.Model):
    status = models.CharField(
        max_length=20,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
        db_index=True
    )

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    execution_time_ms = models.PositiveIntegerField(null=True, blank=True)

    error_message = models.TextField(blank=True)

    class Meta:
        abstract = True


# =========================================================
# 🧠 BASE REPORT (POLYMORPHIC READY)
# =========================================================

class BaseReport(TimeStampedModel, AuditModel, StatusModel, models.Model):
    """
    Core reporting engine abstraction
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    analysis_type = models.CharField(
        max_length=30,
        choices=AnalysisType.choices,
        db_index=True
    )

    parameters = models.JSONField(default=dict, blank=True)
    result_data = models.JSONField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    # =====================================================
    # ⚙️ LIFECYCLE ENGINE
    # =====================================================

    def start(self):
        self.status = ReportStatus.PROCESSING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])

    def complete(self, result=None, execution_time=None):
        self.status = ReportStatus.COMPLETED
        self.completed_at = timezone.now()
        if result is not None:
            self.result_data = result
        if execution_time:
            self.execution_time_ms = execution_time
        self.save()

    def fail(self, error):
        self.status = ReportStatus.FAILED
        self.error_message = str(error)
        self.completed_at = timezone.now()
        self.save()

    def duration(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


# =========================================================
# 📅 TIME SERIES REPORTS
# =========================================================

class DailyReport(BaseReport):
    date = models.DateField(db_index=True)


class WeeklyReport(BaseReport):
    year = models.IntegerField(db_index=True)
    week = models.IntegerField(db_index=True)


class MonthlyReport(BaseReport):
    year = models.IntegerField(db_index=True)
    month = models.IntegerField(db_index=True)


class AnnualReport(BaseReport):
    year = models.IntegerField(db_index=True, unique=True)


# =========================================================
# 🚨 FIXED + SAFE DATE RANGE MODEL (NO DB CONSTRAINT CRASH)
# =========================================================

class CustomDateRangeReport(BaseReport):
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)

    def clean(self):
        super().clean()
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValidationError("start_date must be before end_date")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


# =========================================================
# 📦 FILE STORAGE (NORMALIZED DESIGN)
# =========================================================

class ReportFile(models.Model):
    report_type = models.CharField(max_length=50, db_index=True)
    report_id = models.UUIDField(db_index=True)

    format = models.CharField(max_length=20, choices=ReportFormat.choices)

    file = models.FileField(upload_to="reports/%Y/%m/%d/")

    created_at = models.DateTimeField(auto_now_add=True)


# =========================================================
# 🧠 CACHE ENGINE (FAST LOOKUPS)
# =========================================================

class ReportCache(TimeStampedModel):
    key = models.CharField(max_length=512, unique=True)

    analysis_type = models.CharField(max_length=50)
    parameters_hash = models.CharField(max_length=256, db_index=True)

    result_data = models.JSONField()

    ttl_seconds = models.PositiveIntegerField(default=3600)

    def is_valid(self):
        return (timezone.now() - self.created_at).total_seconds() < self.ttl_seconds


# =========================================================
# 📊 EXECUTION OBSERVABILITY
# =========================================================

class ReportExecutionLog(models.Model):
    report_type = models.CharField(max_length=50, db_index=True)
    report_id = models.UUIDField(db_index=True)

    status = models.CharField(max_length=20)
    execution_time_ms = models.IntegerField(null=True)

    metadata = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)


# =========================================================
# 🔁 VERSIONING SYSTEM (VERY IMPORTANT FOR AI + AUDIT)
# =========================================================

class ReportVersion(models.Model):
    report_type = models.CharField(max_length=50, db_index=True)
    report_id = models.UUIDField(db_index=True)

    version = models.PositiveIntegerField()

    snapshot = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("report_type", "report_id", "version")
