#wsp/models.py
from __future__ import annotations
import uuid
import asyncio
import logging
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.cache import cache
from django.db import models, transaction
from django.db.models import (
    F, Sum, Avg, FloatField, UniqueConstraint, Index, Q
)
from django.utils.text import slugify
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.db.models.signals import post_save
from colorfield.fields import ColorField
from asgiref.sync import async_to_sync

# Optional Celery integration (if available)
try:
    from wsp.tasks import handle_response_postsave
    CELERY_AVAILABLE = True
except Exception:
    CELERY_AVAILABLE = False

# Channels layer
from channels.layers import get_channel_layer

User = get_user_model()
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Abstract Mixins
# ------------------------------------------------------------------------------

class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteMixin(models.Model):
    is_active = models.BooleanField(default=True, db_index=True)

    def delete(self, *args, **kwargs):
        """Soft delete to retain data for analytics consistency."""
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    class Meta:
        abstract = True


class RichDocMixin(models.Model):
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True


class BaseUUID(TimeStamped, SoftDeleteMixin, RichDocMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


# ------------------------------------------------------------------------------
# Core Domain Models
# ------------------------------------------------------------------------------

class Category(BaseUUID):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [Index(fields=["slug"])]
        verbose_name_plural = "Categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    # --- Cached aggregations (with namespace versioning) ---
    def _cache_key(self, survey=None, metric="total"):
        version = cache.get(f"survey:{getattr(survey, 'id', 'all')}:ver", 1)
        return f"cat:{self.id}:surv:{getattr(survey, 'id', 'all')}:v{version}:{metric}"

    def total_score(self, survey=None) -> Decimal:
        key = self._cache_key(survey, "total")
        if cached := cache.get(key):
            return cached

        qs = Response.objects.filter(question__thematic_area__category=self)
        if survey:
            qs = qs.filter(survey=survey)

        total = qs.annotate(
            avg_score=(F("self_option__score") + F("supervisor_option__score")) / 2
        ).aggregate(total=Sum("avg_score"))["total"] or 0.0

        total = Decimal(total)
        cache.set(key, total, timeout=300)
        return total

    def average_score(self, survey=None) -> Decimal:
        key = self._cache_key(survey, "avg")
        if cached := cache.get(key):
            return cached

        qs = Response.objects.filter(question__thematic_area__category=self)
        if survey:
            qs = qs.filter(survey=survey)

        avg = qs.annotate(
            avg_score=(F("self_option__score") + F("supervisor_option__score")) / 2
        ).aggregate(avg=Avg("avg_score"))["avg"] or 0.0

        avg = Decimal(avg)
        cache.set(key, avg, timeout=300)
        return avg


class ThematicArea(BaseUUID):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="areas")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("category", "name")]
        indexes = [Index(fields=["slug"])]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category.name} – {self.name}"

    def total_score(self, survey=None) -> Decimal:
        qs = Response.objects.filter(question__thematic_area=self)
        if survey:
            qs = qs.filter(survey=survey)
        total = qs.annotate(
            avg_score=(F("self_option__score") + F("supervisor_option__score")) / 2
        ).aggregate(total=Sum("avg_score"))["total"] or 0.0
        return Decimal(total)

    def average_score(self, survey=None) -> Decimal:
        qs = Response.objects.filter(question__thematic_area=self)
        if survey:
            qs = qs.filter(survey=survey)
        avg = qs.annotate(
            avg_score=(F("self_option__score") + F("supervisor_option__score")) / 2
        ).aggregate(avg=Avg("avg_score"))["avg"] or 0.0
        return Decimal(avg)


class ThematicGroup(BaseUUID):
    name = models.CharField(max_length=255, unique=True)
    areas = models.ManyToManyField(ThematicArea, related_name="groups", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def total_score(self, survey=None) -> Decimal:
        qs = Response.objects.filter(question__thematic_area__in=self.areas.all())
        if survey:
            qs = qs.filter(survey=survey)
        total = qs.annotate(
            avg_score=(F("self_option__score") + F("supervisor_option__score")) / 2
        ).aggregate(total=Sum("avg_score"))["total"] or 0.0
        return Decimal(total)

    def average_score(self, survey=None) -> Decimal:
        qs = Response.objects.filter(question__thematic_area__in=self.areas.all())
        if survey:
            qs = qs.filter(survey=survey)
        avg = qs.annotate(
            avg_score=(F("self_option__score") + F("supervisor_option__score")) / 2
        ).aggregate(avg=Avg("avg_score"))["avg"] or 0.0
        return Decimal(avg)


class OperationalUnit(BaseUUID):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ------------------------------------------------------------------------------
# Survey and Analytics Models
# ------------------------------------------------------------------------------

class Survey(BaseUUID):
    unit = models.ForeignKey(OperationalUnit, on_delete=models.CASCADE, related_name="surveys")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    share_state = models.CharField(
        max_length=20,
        choices=[("disabled", "Disabled"), ("public", "Public")],
        default="disabled",
    )
    share_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    share_expires_at = models.DateTimeField(null=True, blank=True)
    average_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=["unit", "name"], name="unique_survey_per_unit")]
        indexes = [Index(fields=["slug"]), Index(fields=["share_uuid"])]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def total_score(self) -> Decimal:
        total = self.responses.annotate(
            avg_score=(F("self_option__score") + F("supervisor_option__score")) / 2
        ).aggregate(total=Sum("avg_score"))["total"] or 0.0
        return Decimal(total)

    def recalc_average(self):
        """Recalculate weighted average score."""
        agg = self.responses.annotate(
            weighted_score=((F("self_option__score") + F("supervisor_option__score")) / 2) * F("question__weight")
        ).aggregate(
            total_weighted=Sum("weighted_score"),
            total_weight=Sum("question__weight", output_field=FloatField())
        )
        total_weighted = agg["total_weighted"] or 0.0
        total_weight = agg["total_weight"] or 1.0
        self.average_score = Decimal(total_weighted / total_weight)

    @property
    def completion_rate(self) -> float:
        total_qs = self.responses.values("question").distinct().count()
        answered_qs = self.responses.exclude(Q(self_option=None) & Q(supervisor_option=None)).count()
        return round((answered_qs / total_qs) * 100, 2) if total_qs else 0.0

    def hierarchical_report(self):
        """Nested analytics report for API/GraphQL consumers."""
        report = {}
        areas = (
            ThematicArea.objects
            .filter(questions__responses__survey=self)
            .prefetch_related("questions__options", "category")
            .distinct()
        )
        for area in areas:
            cat_name = area.category.name
            report.setdefault(cat_name, {})
            area_dict = {
                "total_score": float(area.total_score(self)),
                "average_score": float(area.average_score(self)),
                "questions": [
                    {
                        "text": q.text,
                        "weight": float(q.weight),
                        "total_score": float(q.options.aggregate(total=Sum("score"))["total"] or 0.0)
                    }
                    for q in area.questions.all()
                ]
            }
            report[cat_name][area.name] = area_dict
        return report

    def invalidate_cache(self):
        """Increment survey-level cache version."""
        cache.incr(f"survey:{self.id}:ver", ignore_key_check=True)

    def __str__(self):
        return f"{self.name} ({self.unit})"


# ------------------------------------------------------------------------------
# Question Models
# ------------------------------------------------------------------------------

class Question(BaseUUID):
    thematic_area = models.ForeignKey(ThematicArea, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1,
        validators=[MinValueValidator(Decimal("0.1"))]
    )

    class Meta:
        ordering = ["thematic_area__name", "created_at"]

    def __str__(self):
        return self.text[:60]


class Option(BaseUUID):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=255)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    color = ColorField(default="#FFFFFF")

    class Meta:
        ordering = ["created_at"]
        constraints = [UniqueConstraint(fields=["question", "text"], name="uniq_option")]

    def __str__(self):
        return f"{self.text} ({self.score})"


# ------------------------------------------------------------------------------
# Response Models
# ------------------------------------------------------------------------------

class Response(BaseUUID):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="responses")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="responses")
    self_option = models.ForeignKey(
        Option, on_delete=models.SET_NULL, null=True, blank=True, related_name="self_responses"
    )
    supervisor_option = models.ForeignKey(
        Option, on_delete=models.SET_NULL, null=True, blank=True, related_name="supervisor_responses"
    )
    respondent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="submitted_responses"
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="supervised_responses"
    )
    completed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["question__thematic_area__name", "question__text"]
        constraints = [UniqueConstraint(fields=["survey", "question", "respondent"], name="uniq_response_per_user_question")]
        indexes = [Index(fields=["survey", "question"])]

    @property
    def average_score(self) -> Decimal:
        values = [
            self.self_option.score if self.self_option else None,
            self.supervisor_option.score if self.supervisor_option else None
        ]
        values = [v for v in values if v is not None]
        return Decimal(sum(values) / len(values)) if values else Decimal("0")

    async def notify_dashboard(self):
        """Async dashboard notification via Channels."""
        layer = get_channel_layer()
        if not layer:
            return
        group = f"dashboard_updates_{self.survey.unit_id}"
        await layer.group_send(group, {"type": "send_update", "data": {"survey_id": str(self.survey.id)}})

    def save(self, *args, **kwargs):
        """Atomic, async-safe, and optionally Celery-backed save logic."""
        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.survey.recalc_average()
            self.survey.save(update_fields=["average_score"])
            self.survey.invalidate_cache()

        if CELERY_AVAILABLE:
            handle_response_postsave.delay(str(self.pk))
        else:
            # Fallback async notification
            async_to_sync(self.notify_dashboard)()

    def __str__(self):
        return f"{self.survey} – {self.question.text[:40]}"


# ------------------------------------------------------------------------------
# Response History + Signals
# ------------------------------------------------------------------------------

class ResponseHistory(BaseUUID):
    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="history")
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="history")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="history")
    self_option = models.ForeignKey(Option, on_delete=models.SET_NULL, null=True, blank=True, related_name="hist_self_opt")
    supervisor_option = models.ForeignKey(Option, on_delete=models.SET_NULL, null=True, blank=True, related_name="hist_supervisor_opt")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="response_histories")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        indexes = [Index(fields=["survey", "question"])]

    def __str__(self):
        return f"History {self.response_id} @ {self.changed_at}"


@receiver(post_save, sender=Response, dispatch_uid="create_response_history_signal")
def create_response_history(sender, instance, **kwargs):
    """Auto-track every change to a response."""
    try:
        ResponseHistory.objects.create(
            response=instance,
            survey=instance.survey,
            question=instance.question,
            self_option=instance.self_option,
            supervisor_option=instance.supervisor_option,
            user=instance.respondent or instance.supervisor,
        )
    except Exception as e:
        logger.warning(f"Failed to create ResponseHistory: {e}")


# ------------------------------------------------------------------------------
# Dashboard Layout
# ------------------------------------------------------------------------------

class DashboardWidgetLayout(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="widget_layouts")
    unit = models.ForeignKey(OperationalUnit, on_delete=models.CASCADE, null=True, blank=True)
    widget_name = models.CharField(max_length=100)
    x = models.PositiveIntegerField(default=0)
    y = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=4)
    height = models.PositiveIntegerField(default=4)
    collapsed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "unit", "widget_name")
        ordering = ["y", "x"]

    def __str__(self):
        return f"{self.user.username} – {self.widget_name} ({self.x},{self.y})"
