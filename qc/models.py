#qc/models.py
import string
import random
from decimal import Decimal
from datetime import datetime, timedelta, time as dt_time
from django.apps import apps
from django.dispatch import receiver
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count,Q
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_delete, post_migrate, post_save
from accounts.models import CustomUser
from t.models import (
    TreatmentPlant, TreatmentPlantPhase,
    TreatedWaterLimit, RawWaterLimit,
    CoagulatedWaterLimit, ClarifiedWaterLimit,
)
from sc.models import Shift

User = CustomUser

MAX_DIGITS = 10
DECIMAL_PLACES = 3
class SamplingSchedule(models.Model):

    RAW = "raw"
    TREATED = "treated"
    COAGULATED = "coagulated"
    CLARIFIED = "clarified"

    WATER_TYPE_CHOICES = (
        (RAW, "Raw Water"),
        (TREATED, "Treated Water"),
        (COAGULATED, "Coagulated Water"),
        (CLARIFIED, "Clarified Water"),
    )

    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.CASCADE,
        related_name="sampling_schedules",
        db_index=True,
    )

    water_type = models.CharField(
        max_length=32,
        choices=WATER_TYPE_CHOICES,
        db_index=True,
    )

    start_time = models.TimeField(
        help_text="First sampling time."
    )

    interval_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Sampling interval in minutes.",
    )

    enabled = models.BooleanField(
        default=True,
        db_index=True,
    )

    last_generated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )


    class Meta:

        ordering = (
            "treatment_plant",
            "water_type",
        )

        verbose_name = "Sampling Schedule"
        verbose_name_plural = "Sampling Schedules"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "treatment_plant",
                    "water_type",
                ],
                name="uq_sampling_schedule_plant_water_type",
            )
        ]

        indexes = [
            models.Index(
                fields=[
                    "treatment_plant",
                    "water_type",
                ]
            ),
            models.Index(
                fields=[
                    "enabled",
                ]
            ),
            models.Index(
                fields=[
                    "last_generated_at",
                ]
            ),
        ]


    def __str__(self):
        return (
            f"{self.treatment_plant.name} - "
            f"{self.get_water_type_display()} "
            f"({self.interval_minutes} mins)"
        )


    def clean(self):
        super().clean()

        if self.interval_minutes < 1:
            raise ValidationError(
                {
                    "interval_minutes":
                    "Interval must be at least one minute."
                }
            )

        if self.interval_minutes > 1440:
            raise ValidationError(
                {
                    "interval_minutes":
                    "Interval cannot exceed 24 hours."
                }
            )


    @property
    def samples_per_day(self):
        return max(
            1,
            1440 // self.interval_minutes
        )


    @property
    def generated_count(self):
        return self.sampling_times.count()


    @property
    def is_healthy(self):
        return (
            self.generated_count
            == self.samples_per_day
        )


    @property
    def first_sampling(self):
        return (
            self.sampling_times
            .order_by("time")
            .first()
        )


    @property
    def last_sampling(self):
        return (
            self.sampling_times
            .order_by("-time")
            .first()
        )


    @property
    def next_sampling_time(self):
        now = timezone.localtime().time()

        sample = (
            self.sampling_times
            .filter(time__gt=now)
            .order_by("time")
            .first()
        )

        if sample:
            return sample

        return (
            self.sampling_times
            .order_by("time")
            .first()
        )


    @property
    def previous_sampling_time(self):

        now = timezone.localtime().time()

        return (
            self.sampling_times
            .filter(time__lte=now)
            .order_by("-time")
            .first()
        )


    @property
    def next_run_datetime(self):

        sample = self.next_sampling_time

        if not sample:
            return None

        return timezone.make_aware(
            datetime.combine(
                timezone.localdate(),
                sample.time,
            )
        )


    @transaction.atomic
    def generate_times(self):
        current = datetime.combine(
            timezone.localdate(),
            self.start_time,
        )

        end = current + timedelta(days=1)

        desired_times = set()
        while current < end:
            desired_times.add(current.time())
            current += timedelta(
                minutes=self.interval_minutes
            )

        existing_times = set(
            self.sampling_times.values_list("time", flat=True)
        )

        # Delete obsolete times only if they are not referenced by any WaterAnalysis
        self.sampling_times.filter(
            water_analyses__isnull=True
        ).exclude(
            time__in=desired_times
        ).delete()

        # Create new times that don't exist yet
        times_to_create = desired_times - existing_times
        rows = [
            SamplingTime(
                schedule=self,
                time=t,
            )
            for t in sorted(times_to_create)
        ]

        if rows:
            SamplingTime.objects.bulk_create(
                rows,
                batch_size=1000,
                ignore_conflicts=True,
            )

        self.last_generated_at = timezone.now()

        super().save(
            update_fields=[
                "last_generated_at",
            ]
        )


    def save(self, *args, **kwargs):

        self.full_clean()

        regenerate = False

        if self.pk:

            old = (
                SamplingSchedule.objects
                .filter(pk=self.pk)
                .only(
                    "treatment_plant",
                    "start_time",
                    "interval_minutes",
                    "enabled",
                )
                .first()
            )

            if old:

                regenerate = (
                    old.treatment_plant_id
                    != self.treatment_plant_id
                    or
                    old.start_time
                    != self.start_time
                    or
                    old.interval_minutes
                    != self.interval_minutes
                    or
                    old.enabled
                    != self.enabled
                )

        else:
            regenerate = True


        super().save(*args, **kwargs)


        if regenerate:

            if self.enabled:
                self.generate_times()

            else:
                self.sampling_times.filter(water_analyses__isnull=True).delete()
class SamplingTime(models.Model):

    schedule = models.ForeignKey(
        SamplingSchedule,
        on_delete=models.CASCADE,
        related_name="sampling_times",
        db_index=True,
    )

    time = models.TimeField(
        db_index=True,
    )

    class Meta:
        ordering = (
            "schedule__water_type",
            "time",
        )

        verbose_name = "Sampling Time"
        verbose_name_plural = "Sampling Times"

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "schedule",
                    "time",
                ),
                name="uq_sampling_schedule_time",
            )
        ]

        indexes = [
            models.Index(
                fields=(
                    "schedule",
                    "time",
                )
            ),
            models.Index(
                fields=("time",)
            ),
        ]

    def __str__(self):
        return (
            f"{self.schedule.get_water_type_display()} "
            f"{self.time.strftime('%H:%M')}"
        )

    # ======================================================
    # PROPERTIES
    # ======================================================

    @property
    def water_type(self):
        return self.schedule.water_type

    @property
    def display_name(self):
        return (
            f"{self.schedule.get_water_type_display()} "
            f"{self.time.strftime('%H:%M')}"
        )

    @property
    def next_sampling(self):
        nxt = (
            self.schedule.sampling_times
            .filter(time__gt=self.time)
            .order_by("time")
            .first()
        )

        if nxt:
            return nxt

        return (
            self.schedule.sampling_times
            .order_by("time")
            .first()
        )

    @property
    def previous_sampling(self):
        prev = (
            self.schedule.sampling_times
            .filter(time__lt=self.time)
            .order_by("-time")
            .first()
        )

        if prev:
            return prev

        return (
            self.schedule.sampling_times
            .order_by("-time")
            .first()
        )

    @property
    def next_datetime(self):
        """
        Returns the next datetime this sampling
        will occur.
        """

        now = timezone.localtime()

        occurrence = timezone.make_aware(
            datetime.combine(
                now.date(),
                self.time,
            )
        )

        if occurrence <= now:
            occurrence += timedelta(days=1)

        return occurrence

    @property
    def previous_datetime(self):
        """
        Previous occurrence of this sampling.
        """

        now = timezone.localtime()

        occurrence = timezone.make_aware(
            datetime.combine(
                now.date(),
                self.time,
            )
        )

        if occurrence > now:
            occurrence -= timedelta(days=1)

        return occurrence

    @property
    def minutes_until(self):
        """
        Minutes until this sampling occurs.
        """

        return int(
            (
                self.next_datetime
                - timezone.localtime()
            ).total_seconds() // 60
        )

    @property
    def minutes_since(self):
        """
        Minutes since this sampling occurred.
        """

        return int(
            (
                timezone.localtime()
                - self.previous_datetime
            ).total_seconds() // 60
        )

    @property
    def is_due(self):
        """
        Returns True if this sampling should
        already have happened.
        """

        return self.minutes_until == 0

    @property
    def sequence(self):
        """
        Position within the daily cycle.
        """

        return (
            self.schedule.sampling_times
            .filter(time__lte=self.time)
            .count()
        )

    @property
    def total_samples(self):
        return self.schedule.samples_per_day

def generate_reference_id(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class WaterAnalysis(TimeStampedModel):
    reference_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True,
    )

    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.CASCADE,
        related_name="water_analyses",
        db_index=True,
    )

    analysis_date = models.DateField(
        default=timezone.localdate,
        db_index=True,
    )

    shift = models.ForeignKey(
        Shift,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="water_analyses",
    )

    analysis_time = models.ForeignKey(
        SamplingTime,
        on_delete=models.PROTECT,
        related_name="water_analyses",
        db_index=True,
    )

    remarks = models.TextField(
        blank=True,
        null=True,
    )

    class Meta:
        ordering = (
            "-analysis_date",
            "-analysis_time__time",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "treatment_plant",
                    "analysis_date",
                    "analysis_time",
                ),
                name="uq_analysis",
            ),
        ]

        indexes = [
            models.Index(
                fields=(
                    "analysis_date",
                    "treatment_plant",
                )
            ),
            models.Index(
                fields=(
                    "analysis_time",
                    "analysis_date",
                )
            ),
            models.Index(
                fields=("shift",)
            ),
        ]

    def __str__(self):
        return (
            f"{self.treatment_plant.name} | "
            f"{self.analysis_date} | "
            f"{self.analysis_time.time.strftime('%H:%M')}"
        )

    @property
    def water_type(self):
        return self.analysis_time.water_type

    @property
    def phases(self):
        return self.treatment_plant.phases.all()

    def clean(self):
        super().clean()

        if self.shift is None and self.analysis_time_id:
            self.shift = Shift.get_shift_for_time(
                self.analysis_time.time,
                self.treatment_plant,
            )

    def generate_reference(self):
        while True:
            reference = generate_reference_id(10)
            if not WaterAnalysis.objects.filter(
                reference_id=reference
            ).exists():
                return reference

    def generate_results(self):
        from qc.services.result_generator import AnalysisResultGenerator
        return AnalysisResultGenerator.generate_for_analysis(self)

    def save(self, *args, **kwargs):
        if not self.reference_id:
            self.reference_id = self.generate_reference()

        if not self.shift and self.analysis_time_id:
            self.shift = Shift.get_shift_for_time(
                self.analysis_time.time,
                self.treatment_plant,
            )

        super().save(*args, **kwargs)

class BaseResult(TimeStampedModel):
    analysis = models.ForeignKey(
        WaterAnalysis,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        db_index=True,
    )

    phase = models.ForeignKey(
        TreatmentPlantPhase,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)ss",
        db_index=True,
    )

    value = models.DecimalField(
        max_digits=MAX_DIGITS,
        decimal_places=DECIMAL_PLACES,
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True

        ordering = (
            "analysis",
            "phase__name",
            "parameter__parameter__name",
        )

        indexes = [
            models.Index(fields=["analysis"]),
            models.Index(fields=["analysis", "phase"]),
            models.Index(fields=["phase"]),
        ]

    def __str__(self):
        parts = [self.analysis.reference_id, self.parameter.parameter.name]
        if self.phase:
            parts.append(self.phase.name)
        return " | ".join(parts)

    def clean(self):
        super().clean()

        if not self.analysis_id:
            return

        if (
            self.parameter.treatment_plant_id
            != self.analysis.treatment_plant_id
        ):
            raise ValidationError(
                "Parameter limit belongs to a different treatment plant."
            )

        plant = self.analysis.treatment_plant
        has_phases = plant.phases.exists()

        if self.analysis.water_type == SamplingSchedule.RAW:
            if self.phase_id:
                raise ValidationError({
                    "phase": "Raw water results cannot have a treatment phase."
                })
            return

        if has_phases:
            if not self.phase_id:
                raise ValidationError({
                    "phase": "Treatment phase is required."
                })

            if self.phase.treatment_plant_id != plant.id:
                raise ValidationError({
                    "phase": "Selected phase belongs to another treatment plant."
                })
        elif self.phase_id:
            raise ValidationError({
                "phase": "This treatment plant has no phases."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

class RawWaterResult(BaseResult):
    parameter = models.ForeignKey(
        RawWaterLimit,
        on_delete=models.PROTECT,
        related_name="results",
        db_index=True,
    )

    class Meta(BaseResult.Meta):
        verbose_name = "Raw Water Result"
        verbose_name_plural = "Raw Water Results"

        constraints = [
            models.UniqueConstraint(
                fields=("analysis", "parameter"),
                name="uq_raw_analysis_parameter",
            ),
        ]


class TreatedWaterResult(BaseResult):
    parameter = models.ForeignKey(
        TreatedWaterLimit,
        on_delete=models.PROTECT,
        related_name="results",
        db_index=True,
    )

    class Meta(BaseResult.Meta):
        verbose_name = "Treated Water Result"
        verbose_name_plural = "Treated Water Results"

        constraints = [
            # Plants without phases
            models.UniqueConstraint(
                fields=("analysis", "parameter"),
                condition=Q(phase__isnull=True),
                name="uq_treated_result_analysis_parameter",
            ),

            # Plants with phases
            models.UniqueConstraint(
                fields=("analysis", "phase", "parameter"),
                condition=Q(phase__isnull=False),
                name="uq_treated_result_analysis_phase_parameter",
            ),
        ]


class CoagulatedWaterResult(BaseResult):
    parameter = models.ForeignKey(
        CoagulatedWaterLimit,
        on_delete=models.PROTECT,
        related_name="results",
        db_index=True,
    )

    class Meta(BaseResult.Meta):
        verbose_name = "Coagulated Water Result"
        verbose_name_plural = "Coagulated Water Results"

        constraints = [
            models.UniqueConstraint(
                fields=("analysis", "parameter"),
                condition=Q(phase__isnull=True),
                name="uq_coagulated_result_analysis_parameter",
            ),

            models.UniqueConstraint(
                fields=("analysis", "phase", "parameter"),
                condition=Q(phase__isnull=False),
                name="uq_coagulated_result_analysis_phase_parameter",
            ),
        ]


class ClarifiedWaterResult(BaseResult):
    parameter = models.ForeignKey(
        ClarifiedWaterLimit,
        on_delete=models.PROTECT,
        related_name="results",
        db_index=True,
    )

    class Meta(BaseResult.Meta):
        verbose_name = "Clarified Water Result"
        verbose_name_plural = "Clarified Water Results"

        constraints = [
            models.UniqueConstraint(
                fields=("analysis", "parameter"),
                condition=Q(phase__isnull=True),
                name="uq_clarified_result_analysis_parameter",
            ),

            models.UniqueConstraint(
                fields=("analysis", "phase", "parameter"),
                condition=Q(phase__isnull=False),
                name="uq_clarified_result_analysis_phase_parameter",
            ),
        ]
class NonConformityStatus(models.TextChoices):
    OPEN = "open", _("Open")
    UNDER_REVIEW = "under_review", _("Under Review")
    CLOSED = "closed", _("Closed")


class Cause(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_causes")

    def __str__(self):
        return self.name


class NonConformity(TimeStampedModel):
    analysis = models.ForeignKey(WaterAnalysis, on_delete=models.CASCADE, related_name='nonconformities')
    parameter_name = models.CharField(max_length=128)
    observed_value = models.FloatField()
    min_limit = models.FloatField()
    max_limit = models.FloatField()
    deviation = models.FloatField()
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="triggered_nonconformities")
    auto_detected = models.BooleanField(default=True)
    status = models.CharField(max_length=32, choices=NonConformityStatus.choices, default=NonConformityStatus.OPEN)
    corrective_action = models.TextField(blank=True, null=True)
    preventive_action = models.TextField(blank=True, null=True)
    root_cause = models.TextField(blank=True, null=True)
    causes = models.ManyToManyField(Cause, blank=True, related_name="nonconformities")
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_nonconformities")
    resolved_at = models.DateTimeField(null=True, blank=True)
    escalation_level = models.PositiveIntegerField(default=0)
    risk_score = models.FloatField(default=0.0)

    def __str__(self):
        return f"NC-{self.parameter_name} ({self.status})"

    def _log(self, actor, action, remarks, auto=True):
        NonConformityLog.objects.create(
            nonconformity=self,
            actor=actor,
            action=action,
            remarks=remarks,
            auto_generated=auto,
        )

    def close(self, actor=None, remarks=""):
        self.status = NonConformityStatus.CLOSED
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "resolved_at"])
        self._log(actor, "closed", remarks or "Closed after CAPA implementation.")

    def evaluate_risk(self):
        deviation_pct = abs(self.deviation) / max(self.max_limit, 1)
        score = 1 + (deviation_pct * 5)
        self.risk_score = round(min(score, 10.0), 2)
        self.save(update_fields=["risk_score"])
        return self.risk_score


def detect_nonconformity(parameter_limit, result_value, analysis, user=None):
    if not parameter_limit:
        return

    min_val = float(parameter_limit.min_value or 0)
    max_val = float(parameter_limit.max_value or 0)
    result_val = float(result_value)

    if result_val < min_val or result_val > max_val:
        deviation = abs(result_val - (min_val if result_val < min_val else max_val))
        nc = NonConformity.objects.create(
            analysis=analysis,
            parameter_name=str(parameter_limit.parameter),
            observed_value=result_val,
            min_limit=min_val,
            max_limit=max_val,
            deviation=deviation,
            triggered_by=user,
            auto_detected=True,
        )
        nc.evaluate_risk()
        nc._log(user, "auto_detected", f"Detected deviation {result_val} (limits: {min_val}-{max_val})")
    else:
        open_ncs = NonConformity.objects.filter(
            analysis=analysis,
            parameter_name=str(parameter_limit.parameter),
            status__in=[NonConformityStatus.OPEN, NonConformityStatus.UNDER_REVIEW]
        )
        for nc in open_ncs:
            nc.close(actor=user, remarks=f"Value {result_val} returned to normal range ({min_val}-{max_val}).")



class NonConformityLog(TimeStampedModel):
    nonconformity = models.ForeignKey(NonConformity, on_delete=models.CASCADE, related_name='logs')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=64)
    remarks = models.TextField(blank=True, null=True)
    auto_generated = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} on {self.nonconformity} by {self.actor or 'System'}"


class WaterAnalysisLog(TimeStampedModel):
    analysis = models.ForeignKey(WaterAnalysis, on_delete=models.CASCADE, related_name='logs')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=64)
    remarks = models.TextField(blank=True, null=True)
    auto_generated = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} on {self.analysis.reference_id} by {self.actor or 'System'}"
