#sc/models.py
from __future__ import annotations
import threading
from datetime import  timedelta as py_timedelta
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from typing import Optional, List, Dict, Tuple
from django.db import models, transaction
from calendar import monthrange
from django.contrib.auth import get_user_model
from collections import defaultdict
from typing import List, Optional
from django.utils import timezone
from t.models import TreatmentPlant
from inventory.models import (Equipment, Status)
from django.conf import settings
from datetime import datetime, date, timedelta
from django.core.exceptions import ValidationError
from django.db import models
from core.models import Section
from django.contrib.postgres.fields import DateTimeRangeField

User = get_user_model()

# -------------------------------
_STATUS_CACHE: Dict[str, Status] = {}
_STATUS_CACHE_LOCK = threading.Lock()
_STATUS_CACHE_TTL = 60  # seconds
_STATUS_CACHE_TS: Dict[str, float] = {}


def get_status_by_name(name: str) -> Optional[Status]:
    """Retrieve Status by name with cache and TTL."""
    if not name:
        return None
    key = name.strip().lower()
    now_ts = timezone.now().timestamp()
    with _STATUS_CACHE_LOCK:
        if key in _STATUS_CACHE and now_ts - _STATUS_CACHE_TS.get(key, 0) < _STATUS_CACHE_TTL:
            return _STATUS_CACHE[key]
    status = Status.objects.filter(name__iexact=name).first()
    if status:
        with _STATUS_CACHE_LOCK:
            _STATUS_CACHE[key] = status
            _STATUS_CACHE_TS[key] = now_ts
    return status

def invalidate_status_cache(name: Optional[str] = None) -> None:
    """Invalidate cache optionally for a single name."""
    with _STATUS_CACHE_LOCK:
        if name:
            key = name.strip().lower()
            _STATUS_CACHE.pop(key, None)
            _STATUS_CACHE_TS.pop(key, None)
        else:
            _STATUS_CACHE.clear()
            _STATUS_CACHE_TS.clear()

# -------------------------------
# Audit Mixin
# -------------------------------
TRACKED_MODELS: set[str] = set()

class AuditMixin:
    """Add as a base for models you want audited manually."""
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        try:
            TRACKED_MODELS.add(cls._meta.model_name)
        except Exception:
            pass

    @staticmethod
    def create_audit(
        user: Optional[settings.AUTH_USER_MODEL],
        action: str,
        instance: models.Model,
        before: Optional[dict] = None,
        after: Optional[dict] = None
    ) -> None:
        ct = ContentType.objects.get_for_model(instance.__class__)
        AuditLog.objects.create(
            user=user,
            action=action,
            content_type=ct,
            object_id=str(getattr(instance, "pk", "")),
            object_repr=str(instance)[:512],
            changes={"before": before, "after": after} if (before or after) else None,
        )

# -------------------------------
# AuditLog
# -------------------------------
class AuditLog(models.Model):
    ACTION_CHOICES = [("create", "Create"), ("update", "Update"), ("delete", "Delete")]

    timestamp: datetime = models.DateTimeField(auto_now_add=True)
    user: Optional[settings.AUTH_USER_MODEL] = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sc_audit_logs"
    )
    action: str = models.CharField(max_length=10, choices=ACTION_CHOICES)
    content_type: ContentType = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="sc_audit_logs")
    object_id: str = models.CharField(max_length=255)
    content_object: GenericForeignKey = GenericForeignKey("content_type", "object_id")
    object_repr: str = models.CharField(max_length=512)
    changes: Optional[dict] = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self) -> str:
        return f"[{self.timestamp}] {self.action.upper()} {self.content_type.app_label}.{self.content_type.model}({self.object_id})"

# -------------------------------
# SoftDeleteMixin
# -------------------------------
class SoftDeleteQuerySet(models.QuerySet):
    def active(self) -> models.QuerySet:
        return self.filter(is_deleted=False)

class SoftDeleteMixin(models.Model):
    is_deleted: bool = models.BooleanField(default=False)
    deleted_at: Optional[datetime] = models.DateTimeField(null=True, blank=True)

    objects: SoftDeleteQuerySet = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False) -> None:
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

# -------------------------------
# Shift Manager
# -------------------------------
class ShiftManager(models.Manager):
    def active(self) -> models.QuerySet:
        return self.get_queryset().filter(is_deleted=False)

    def for_treatment_plant(self, tp: TreatmentPlant) -> models.QuerySet:
        return self.active().filter(treatment_plant=tp)

# -------------------------------
# MonthlyDutyRosterManager
# -------------------------------
class MonthlyDutyRosterManager(models.Manager):
    def for_month_year(self, month: int, year: int, treatment_plant: Optional[TreatmentPlant] = None) -> models.QuerySet:
        qs = self.get_queryset().filter(month=month, year=year)
        if treatment_plant:
            qs = qs.filter(treatment_plant=treatment_plant)
        return qs

# ==========================================================
# SHIFT
# ==========================================================

class Shift(SoftDeleteMixin, models.Model):
    name = models.CharField(max_length=50)
    start_time = models.TimeField()
    end_time = models.TimeField()
    handover_time = models.TimeField(
        null=True,
        blank=True,)
    takeover_time = models.TimeField(
        null=True,
        blank=True,)
    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.CASCADE,
        related_name="shifts",
    )

    time_range = DateTimeRangeField(
        null=True,
        blank=True,
        editable=False,
    )

    objects = ShiftManager()

    class Meta:
        ordering = [
            "treatment_plant",
            "start_time",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "treatment_plant",
                    "name",
                ],
                name="unique_shift_name_per_plant",
            ),
        ]

    def __str__(self):
        return (
            f"{self.name} "
            f"({self.start_time:%H:%M}"
            f" → "
            f"{self.end_time:%H:%M})"
        )

    @property
    def is_overnight(self):
        return self.end_time <= self.start_time

    @property
    def duration(self):
        start = datetime.combine(date.today(), self.start_time)
        end = datetime.combine(date.today(), self.end_time)

        if self.is_overnight:
            end += timedelta(days=1)

        return end - start

    @classmethod
    def get_shift_for_time(
            cls,
            sample_time,
            treatment_plant=None,
    ):

        qs = cls.objects.active()

        if treatment_plant:
            qs = qs.filter(
                treatment_plant=treatment_plant
            )

        if isinstance(sample_time, datetime):

            if timezone.is_aware(sample_time):
                current_datetime = timezone.localtime(sample_time)
            else:
                current_datetime = timezone.make_aware(sample_time)

            current_time = current_datetime.time()

        else:
            current_time = sample_time

        shifts = list(
            qs.order_by(
                "start_time"
            )
        )

        for shift in shifts:

            start = shift.start_time
            end = shift.end_time

            # ------------------------------
            # Normal shift
            # Example:
            # 08:00 - 16:00
            # ------------------------------
            if not shift.is_overnight:

                if start <= current_time < end:
                    return shift


            # ------------------------------
            # Overnight shift
            # Example:
            # 16:00 - 00:00
            # 22:00 - 06:00
            # ------------------------------
            else:

                if (
                        current_time >= start
                        or
                        current_time < end
                ):
                    return shift

        return None

    @classmethod
    def get_shift_map(
            cls,
            times,
            treatment_plant=None,
    ):

        qs = cls.objects.active()

        if treatment_plant:
            qs = qs.filter(
                treatment_plant=treatment_plant
            )

        shifts = list(qs)

        mapping = {}

        for item in times:

            if isinstance(item, datetime):

                if timezone.is_aware(item):
                    current_time = timezone.localtime(item).time()
                else:
                    current_time = item.time()

            else:
                current_time = item

            mapping[item] = None

            for shift in shifts:

                start = shift.start_time
                end = shift.end_time

                if not shift.is_overnight:

                    if start <= current_time < end:
                        mapping[item] = shift
                        break


                else:

                    if (
                            current_time >= start
                            or
                            current_time < end
                    ):
                        mapping[item] = shift
                        break

        return mapping


    def _minutes(t):
        return (
                t.hour * 60
                +
                t.minute
        )

    def clean(self):

        if self.start_time == self.end_time:
            raise ValidationError(
                "Start and end time cannot be identical."
            )

        start = _minutes(self.start_time)
        end = _minutes(self.end_time)

        if end <= start:
            end += 1440

        for other in (
                Shift.objects.active()
                        .filter(
                    treatment_plant=self.treatment_plant
                )
                        .exclude(pk=self.pk)
        ):

            other_start = _minutes(
                other.start_time
            )

            other_end = _minutes(
                other.end_time
            )

            if other_end <= other_start:
                other_end += 1440

            ranges = [
                (start, end),
                (other_start, other_end),
                (other_start + 1440, other_end + 1440),
            ]

            if any(
                    a < d and c < b
                    for a, b in [(start, end)]
                    for c, d in [
                        (other_start, other_end),
                        (other_start + 1440, other_end + 1440),
                    ]
            ):
                raise ValidationError(
                    f"Shift overlaps with '{other.name}'."
                )

    def save(self, *args, **kwargs):

        self.full_clean()

        start = datetime.combine(
            date.today(),
            self.start_time,
        )

        end = datetime.combine(
            date.today(),
            self.end_time,
        )

        if self.is_overnight:
            end += timedelta(days=1)

        self.time_range = (
            start,
            end,
        )

        super().save(*args, **kwargs)

    def get_requirement(self, section):

        return self.section_requirements.filter(
            section=section
        ).first()

    def get_required_staff(
        self,
        section,
        day_type,
    ):

        requirement = self.get_requirement(section)

        if requirement is None:
            return 0

        return requirement.get_required_staff(
            day_type
        )


class ShiftSectionRequirement(models.Model):
    shift = models.ForeignKey(
        Shift,
        on_delete=models.CASCADE,
        related_name="section_requirements",
    )

    section = models.ForeignKey(
        "core.Section",
        on_delete=models.CASCADE,
        related_name="shift_requirements",)
    weekday_required = models.PositiveSmallIntegerField(default=1,)
    weekend_required = models.PositiveSmallIntegerField(default=1,)
    holiday_required = models.PositiveSmallIntegerField(default=1,)
    minimum_required = models.PositiveSmallIntegerField(default=1,)
    preferred_required = models.PositiveSmallIntegerField(default=1,)
    maximum_allowed = models.PositiveSmallIntegerField(default=20,)
    class Meta:
        ordering = [ "shift","section", ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "shift",
                    "section",
                ],
                name="unique_shift_section_requirement",
            ),
        ]

    def __str__(self):

        return (
            f"{self.shift.name} - "
            f"{self.section}"
        )

    def get_required_staff(
        self,
        day_type,
    ):

        if (
            day_type ==
            ShiftAssignment.DAYTYPE_WEEKEND
        ):
            return self.weekend_required

        if (
            day_type ==
            ShiftAssignment.DAYTYPE_HOLIDAY
        ):
            return self.holiday_required

        return self.weekday_required

    def is_understaffed(
        self,
        assigned_count,
        day_type,
    ):

        return (
            assigned_count <
            self.get_required_staff(day_type)
        )

    def is_overstaffed(
        self,
        assigned_count,
    ):

        return (
            assigned_count >
            self.maximum_allowed
        )

    def has_optimal_staff(
        self,
        assigned_count,
    ):

        return (
            self.minimum_required
            <= assigned_count
            <= self.maximum_allowed
        )

class ShiftSupervisor(models.Model):
    treatment_plant: TreatmentPlant = models.ForeignKey(
        TreatmentPlant, on_delete=models.CASCADE, related_name='supervisors'
    )
    user: settings.AUTH_USER_MODEL = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shift_supervisor'
    )
    is_active: bool = models.BooleanField(default=True)

    class Meta:
        unique_together = ('treatment_plant', 'user')

    @property
    def section(self) -> Optional[str]:
        return getattr(self.user, 'section', None)

    def __str__(self) -> str:
        return f"{self.user.get_full_name()} @ {self.treatment_plant.name}"


class ShiftAssignment(AuditMixin, SoftDeleteMixin, models.Model):
    # -----------------------------
    # Attendance
    # -----------------------------
    ATTENDANCE_PRESENT = 'present'
    ATTENDANCE_ABSENT = 'absent'
    ATTENDANCE_LATE = 'late'
    ATTENDANCE_EXCUSED = 'excused'
    ATTENDANCE_CHOICES = [
        (ATTENDANCE_PRESENT, 'Present'),
        (ATTENDANCE_ABSENT, 'Absent'),
        (ATTENDANCE_LATE, 'Late'),
        (ATTENDANCE_EXCUSED, 'Excused')
    ]

    # -----------------------------
    # Day type
    # -----------------------------
    DAYTYPE_WEEKDAY = 'weekday'
    DAYTYPE_WEEKEND = 'weekend'
    DAYTYPE_HOLIDAY = 'holiday'
    DAYTYPE_CHOICES = [
        (DAYTYPE_WEEKDAY, 'Weekday'),
        (DAYTYPE_WEEKEND, 'Weekend'),
        (DAYTYPE_HOLIDAY, 'Holiday')
    ]

    # -----------------------------
    # Fields
    # -----------------------------
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shift_assignments'
    )
    shift = models.ForeignKey(
        'Shift',
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    date = models.DateField()
    day_type = models.CharField(
        max_length=10,
        choices=DAYTYPE_CHOICES,
        default=DAYTYPE_WEEKDAY,
        help_text="Automatically populated: weekday, weekend, or holiday"
    )
    attendance_status = models.CharField(max_length=10, choices=ATTENDANCE_CHOICES, default=ATTENDANCE_PRESENT)
    remarks = models.TextField(blank=True, null=True)
    duty_roster = models.ForeignKey(
        'MonthlyDutyRoster',
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supervised_assignments'
    )
    reassigned_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reassignments'
    )
    handover_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    reassigned_at = models.DateTimeField(null=True, blank=True)
    temp_supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='temp_supervised_assignments'
    )
    temp_supervisor_start = models.DateTimeField(null=True, blank=True)
    temp_supervisor_end = models.DateTimeField(null=True, blank=True)

    # -----------------------------
    # Meta
    # -----------------------------
    class Meta:
        unique_together = ('staff', 'date', 'shift')
        ordering = ['date', 'shift']

    # -----------------------------
    # Properties
    # -----------------------------
    @property
    def week(self):
        return self.date.isocalendar()[1] if self.date else None

    @property
    def section(self):
        return self.staff.section if self.staff else None

    @property
    def is_supervised(self):
        return self.supervisor is not None

    @property
    def duration(self):
        if self.shift and self.shift.start_time and self.shift.end_time:
            start_dt = datetime.combine(date.min, self.shift.start_time)
            end_dt = datetime.combine(date.min, self.shift.end_time)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            return (end_dt - start_dt).total_seconds() / 3600
        return None

    @property
    def effective_supervisor(self):
        self.check_revert_temp_supervisor()
        return self.temp_supervisor if self.temp_supervisor else self.supervisor

    # -----------------------------
    # Methods
    # -----------------------------
    def assign_temp_supervisor(self, new_supervisor, duration_hours=3):
        if self.attendance_status != self.ATTENDANCE_PRESENT:
            raise ValueError(f"{self.staff} is not present and cannot supervise.")

        now = timezone.now()
        end_time = now + timedelta(hours=duration_hours)
        old_temp = self.temp_supervisor

        self.attendance_status = self.ATTENDANCE_EXCUSED
        self.temp_supervisor = new_supervisor
        self.temp_supervisor_start = now
        self.temp_supervisor_end = end_time
        self.save(update_fields=['attendance_status', 'temp_supervisor', 'temp_supervisor_start', 'temp_supervisor_end'])

        AuditMixin.create_audit(
            user=new_supervisor,
            action="update",
            instance=self,
            before={"temp_supervisor": old_temp.id if old_temp else None, "supervisor_status": self.ATTENDANCE_PRESENT},
            after={"temp_supervisor": new_supervisor.id, "duration_hours": duration_hours, "supervisor_status": self.ATTENDANCE_EXCUSED}
        )

    def check_revert_temp_supervisor(self):
        if self.temp_supervisor and self.temp_supervisor_end and timezone.now() >= self.temp_supervisor_end:
            old_temp = self.temp_supervisor
            self.temp_supervisor = None
            self.temp_supervisor_start = None
            self.temp_supervisor_end = None
            self.attendance_status = self.ATTENDANCE_PRESENT
            self.save(update_fields=['temp_supervisor', 'temp_supervisor_start', 'temp_supervisor_end', 'attendance_status'])

            AuditMixin.create_audit(
                user=self.staff,
                action="update",
                instance=self,
                before={"temp_supervisor": old_temp.id},
                after={"temp_supervisor": None, "attendance_status": self.ATTENDANCE_PRESENT}
            )

    def mark_attendance(self, status, remarks=None):
        old_status = self.attendance_status
        old_remarks = self.remarks
        self.attendance_status = status
        if remarks is not None:
            self.remarks = remarks
        self.save(update_fields=['attendance_status', 'remarks'])

        AuditMixin.create_audit(
            user=self.staff,
            action='update',
            instance=self,
            before={'attendance_status': old_status, 'remarks': old_remarks},
            after={'attendance_status': status, 'remarks': self.remarks}
        )

    def record_handover(self, handover=None, taken_over_by=None, notes="", merge_pending=True):
        from sc.models import ShiftHandover

        if handover is None:
            pending_summary = f"Remarks: {self.remarks or 'No remarks'}" if merge_pending else ""
            handover = ShiftHandover.objects.create(
                shift=self.shift,
                date=self.date,
                outgoing_supervisor=self.staff,
                incoming_supervisor=taken_over_by,
                handover_notes=notes,
                pending_work=pending_summary,
                is_taken_over=True,
                taken_over_at=timezone.now()
            )
            AuditMixin.create_audit(
                user=self.staff,
                action="create",
                instance=handover,
                after={
                    "incoming_supervisor": taken_over_by.id if taken_over_by else None,
                    "handover_notes": notes,
                    "is_taken_over": True,
                    "pending_work": pending_summary
                }
            )

        old_handover_to = self.handover_to
        self.handover_to = handover.incoming_supervisor
        self.save(update_fields=['handover_to'])

        AuditMixin.create_audit(
            user=self.staff,
            action="update",
            instance=self,
            before={"handover_to": old_handover_to.id if old_handover_to else None},
            after={"handover_to": handover.incoming_supervisor.id if handover.incoming_supervisor else None}
        )

        return handover

    @classmethod
    def bulk_record_handover(cls, assignments, handover):
        if not handover.incoming_supervisor:
            return

        assignment_ids = [a.id for a in assignments]
        cls.objects.filter(id__in=assignment_ids).update(handover_to=handover.incoming_supervisor)

        # Batch audit logs
        audit_logs = []
        now = timezone.now()
        content_type_id = ContentType.objects.get_for_model(cls).id
        for assignment in assignments:
            old_val = assignment.handover_to.id if assignment.handover_to else None
            audit_logs.append(AuditLog(
                user=assignment.staff,
                action='update',
                content_type_id=content_type_id,
                object_id=assignment.id,
                object_repr=str(assignment),
                changes={'handover_to': {'before': old_val, 'after': handover.incoming_supervisor.id}},
                timestamp=now
            ))
        AuditLog.objects.bulk_create(audit_logs)

    def reassign_to_shift(self, new_shift):
        if self.shift == new_shift:
            return self

        old_shift = self.shift
        old_handover_to = self.handover_to

        self.delete()
        self.reassigned_at = timezone.now()
        AuditMixin.create_audit(
            user=self.staff,
            action="update",
            instance=self,
            before={
                "shift": old_shift.id,
                "handover_to": old_handover_to.id if old_handover_to else None
            },
            after={
                "shift": new_shift.id,
                "handover_to": None,
                "is_deleted": True,
                "reassigned_at": self.reassigned_at.isoformat()
            }
        )

        new_assignment = ShiftAssignment.objects.create(
            staff=self.staff,
            shift=new_shift,
            date=self.date,
            duty_roster=self.duty_roster,
            reassigned_from=self
        )
        AuditMixin.create_audit(
            user=self.staff,
            action="create",
            instance=new_assignment
        )

        return new_assignment


class MonthlyDutyRoster(AuditMixin, models.Model):
    month = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 13)])
    year = models.PositiveIntegerField()
    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.CASCADE,
        related_name='monthly_rosters'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_rosters"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    objects = MonthlyDutyRosterManager()

    class Meta:
        unique_together = ('month', 'year', 'treatment_plant')
        ordering = ['-year', '-month']

    def clean(self) -> None:
        """Ensure month/year is valid."""
        try:
            date(self.year, self.month, 1)
        except ValueError:
            raise ValidationError("Invalid month/year combination")

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        with transaction.atomic():
            super().save(*args, **kwargs)

    @staticmethod
    def get_weeks_in_month(year: int, month: int) -> list[tuple[date, date]]:
        """Return list of (week_start, week_end) tuples for the month (Monday → Sunday)."""
        weeks = []
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        current_monday = first_day - timedelta(days=first_day.weekday())

        while current_monday <= last_day:
            week_start = max(current_monday, first_day)
            week_end = min(current_monday + timedelta(days=6), last_day)
            weeks.append((week_start, week_end))
            current_monday += timedelta(days=7)
        return weeks

    @staticmethod
    def assign_monthly_shifts_bulk(
            duty_roster: "MonthlyDutyRoster",
            section,
            holidays: Optional[list[date]] = None,
    ) -> None:
        holidays = set(holidays or [])

        with transaction.atomic():

            MonthlyDutyRoster.objects.select_for_update().get(pk=duty_roster.pk )
            shifts = list(
                Shift.objects.filter(
                    treatment_plant=duty_roster.treatment_plant,
                    is_deleted=False,
                )
                .prefetch_related("section_requirements")
                .order_by("start_time")
            )

            if not shifts:
                return

            requirement_map = {
                (req.shift_id, req.section_id): req
                for shift in shifts
                for req in shift.section_requirements.all()}
            staff_list = list(
                settings.AUTH_USER_MODEL.objects.filter(
                    assigned_treatment_plant=duty_roster.treatment_plant,
                    section=section,
                    is_active=True,
                ).order_by("id"))

            if not staff_list:
                return

            staff_lookup = {s.id: s for s in staff_list}
            supervisors = list(
                ShiftSupervisor.objects.filter(
                    treatment_plant=duty_roster.treatment_plant,
                    user__section=section,
                    is_active=True,
                ).select_related("user")
            )

            supervisor_cycle = [s.user for s in supervisors]
            existing = list(
                ShiftAssignment.objects.filter(
                    duty_roster=duty_roster,
                    staff__section=section,
                    is_deleted=False,
                ).select_related("staff", "shift")
            )

            existing_by_shift = defaultdict(set)
            staff_load = defaultdict(int)
            last_shift = {}

            for assignment in existing:
                existing_by_shift[
                    (assignment.date, assignment.shift_id)
                ].add(assignment.staff_id)

                staff_load[assignment.staff_id] += 1

                last_shift[assignment.staff_id] = (
                    assignment.date,
                    assignment.shift,
                )
            rotation_seed = duty_roster.month + duty_roster.year
            staff_order = sorted(
                staff_list,
                key=lambda s: (
                    staff_load[s.id],
                    (s.id + rotation_seed) % len(staff_list),),)
            new_assignments = []

            for week_start, week_end in MonthlyDutyRoster.get_weeks_in_month(duty_roster.year,duty_roster.month,):

                current = week_start

                while current <= week_end:

                    if current in holidays:
                        day_type = ShiftAssignment.DAYTYPE_HOLIDAY

                    elif current.weekday() >= 5:
                        day_type = ShiftAssignment.DAYTYPE_WEEKEND

                    else:
                        day_type = ShiftAssignment.DAYTYPE_WEEKDAY

                    for shift in shifts:

                        req = requirement_map.get(
                            (shift.id, section.id)
                        )

                        if req is None:
                            continue

                        required = req.get_required_staff(day_type)

                        assigned = existing_by_shift.setdefault(
                            (current, shift.id),
                            set(),
                        )

                        if len(assigned) >= required:
                            continue

                        candidates = []
                        for staff in staff_order:
                            if staff.id in assigned:
                                continue
                            previous = last_shift.get(staff.id)
                            if previous:
                                prev_date, prev_shift = previous
                                if (
                                        prev_shift.is_overnight
                                        and prev_date == current - timedelta(days=1)
                                        and shift.start_time < prev_shift.end_time
                                ):
                                    continue
                            candidates.append(staff)
                        candidates.sort(
                            key=lambda s: (
                                staff_load[s.id],
                                (s.id + current.day) % len(staff_list),))
                        needed = required - len(assigned)
                        for staff in candidates[:needed]:
                            new_assignments.append(
                                ShiftAssignment(
                                    duty_roster=duty_roster,
                                    shift=shift,
                                    staff=staff,
                                    date=current,
                                    day_type=day_type,
                                )
                            )
                            assigned.add(staff.id)
                            staff_load[staff.id] += 1
                            last_shift[staff.id] = (current,shift, )

                    current += timedelta(days=1)

            if new_assignments:
                ShiftAssignment.objects.bulk_create(
                    new_assignments,
                    batch_size=1000,
                    ignore_conflicts=True,
                )

            # -----------------------------------------------------
            # Supervisor assignment
            # -----------------------------------------------------

            if not supervisor_cycle:
                return

            assignments = list(
                ShiftAssignment.objects.filter(
                    duty_roster=duty_roster,
                    staff__section=section,
                    is_deleted=False,
                )
                .select_related("shift")
                .order_by(
                    "date",
                    "shift__start_time",
                )
            )

            updates = []

            supervisor_index = 0

            for assignment in assignments:

                supervisor = supervisor_cycle[
                    supervisor_index % len(supervisor_cycle)
                    ]

                supervisor_index += 1

                if assignment.supervisor_id != supervisor.id:
                    assignment.supervisor = supervisor
                    updates.append(assignment)

            if updates:
                ShiftAssignment.objects.bulk_update(
                    updates,
                    ["supervisor"],
                    batch_size=1000,
                )

            # -----------------------------------------------------
            # Existing handovers
            # -----------------------------------------------------

            existing_handovers = {
                (h.shift_id, h.date)
                for h in ShiftHandover.objects.filter(
                    shift__treatment_plant=duty_roster.treatment_plant,
                    date__year=duty_roster.year,
                    date__month=duty_roster.month,
                )
            }

            handovers = []

            for assignment in assignments:

                key = (
                    assignment.shift_id,
                    assignment.date,
                )

                if key in existing_handovers:
                    continue

                existing_handovers.add(key)

                handovers.append(
                    ShiftHandover(
                        shift=assignment.shift,
                        date=assignment.date,
                        incoming_supervisor=assignment.supervisor,
                        handover_notes=(
                            f"Automatic handover for "
                            f"{assignment.shift.name}"
                        ),
                    )
                )

            if handovers:
                ShiftHandover.objects.bulk_create(
                    handovers,
                    batch_size=1000,
                    ignore_conflicts=True,
                )
class ShiftHandover(AuditMixin, models.Model):
    shift = models.ForeignKey(
        'Shift',
        on_delete=models.CASCADE,
        related_name='handovers'
    )
    date = models.DateField()

    outgoing_supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handovers_given'
    )
    incoming_supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handovers_taken'
    )

    handover_notes = models.TextField(blank=True, null=True)
    pending_work = models.TextField(blank=True, null=True)

    handed_over_at = models.DateTimeField(auto_now_add=True)
    takeover_notes = models.TextField(blank=True, null=True)
    taken_over_at = models.DateTimeField(blank=True, null=True)

    is_taken_over = models.BooleanField(default=False)

    class Meta:
        unique_together = ('shift', 'date')
        ordering = ['-date', 'shift']

    def __str__(self):
        return f"Handover ({self.date}) - {self.shift.name} [{self.outgoing_supervisor} ➔ {self.incoming_supervisor}]"

    @property
    def expected_handover_time(self):
        return self.shift.handover_time

    @property
    def expected_takeover_time(self):
        return self.shift.takeover_time

    def clean(self):
        """Ensure handover/takeover occur within ±15 minutes of expected shift times."""
        for dt_field, expected_time, label in [
            ('handed_over_at', self.expected_handover_time, "Handover"),
            ('taken_over_at', self.expected_takeover_time, "Takeover")
        ]:
            actual = getattr(self, dt_field)
            if actual:
                expected_dt = datetime.combine(self.date, expected_time)
                window_start = expected_dt - timedelta(minutes=15)
                window_end = expected_dt + timedelta(minutes=15)
                if not (window_start <= actual <= window_end):
                    raise ValidationError(
                        f"{label} must occur within ±15 minutes of {expected_time.strftime('%H:%M')}."
                    )

    @classmethod
    def create_for_shift_bulk(cls, shift, date_, outgoing_supervisor=None, incoming_supervisor=None, notes=""):
        """
        Fully bulked handover creation: autopick supervisors and bulk-update all assignments.
        """
        assignments_qs = ShiftAssignment.objects.filter(
            shift=shift,
            date=date_,
            is_deleted=False
        ).select_related('staff', 'supervisor')

        assignments = list(assignments_qs)

        # Compile pending work
        pending_summary = "\n".join(
            f"{a.staff.get_full_name()}: {getattr(a, 'remarks', 'No remarks')}"
            for a in assignments
        ) or "No pending work."

        # Auto-pick outgoing supervisor if missing
        if not outgoing_supervisor and assignments:
            section_name = assignments[0].staff.section
            eligible = ShiftSupervisor.objects.filter(
                treatment_plant=shift.treatment_plant,
                user__section=section_name,
                is_active=True
            ).order_by('user__id')
            outgoing_supervisor = eligible.first().user if eligible.exists() else None

        # Default incoming supervisor
        if not incoming_supervisor:
            incoming_supervisor = outgoing_supervisor

        with transaction.atomic():
            # Create handover
            handover = cls.objects.create(
                shift=shift,
                date=date_,
                outgoing_supervisor=outgoing_supervisor,
                incoming_supervisor=incoming_supervisor,
                handover_notes=notes,
                pending_work=pending_summary,
                is_taken_over=bool(incoming_supervisor)
            )

            # Bulk update all assignments at once
            if assignments:
                assignments_qs.update(handover_to=incoming_supervisor)

                # Bulk audit creation
                audit_entries = [
                    AuditMixin(
                        user=a.staff,
                        action="update",
                        instance=a,
                        before={"handover_to": getattr(a, 'supervisor_id', None)},
                        after={"handover_to": incoming_supervisor.id if incoming_supervisor else None}
                    )
                    for a in assignments
                ]
                AuditMixin.objects.bulk_create(audit_entries)

            # Audit the handover creation
            AuditMixin.create_audit(
                user=outgoing_supervisor,
                action="create",
                instance=handover,
                after={"pending_work": pending_summary}
            )

        return handover

class Apparatus(AuditMixin, models.Model):
    name = models.CharField(max_length=100, unique=True)
    equipment = models.OneToOneField(Equipment, on_delete=models.CASCADE, related_name='apparatus')
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

APPARATUS_STATUS_CHOICES = [
    ('working', 'Working'),
    ('needs_repair', 'Needs Repair'),
    ('out_of_service', 'Out of Service'),
]
class ApparatusCondition(AuditMixin, models.Model):
    handover = models.ForeignKey(
        ShiftHandover,
        on_delete=models.CASCADE,
        related_name='apparatus_conditions'
    )
    apparatus = models.ForeignKey(
        Apparatus,
        on_delete=models.CASCADE,
        related_name='conditions'
    )
    status = models.CharField(
        max_length=20,
        choices=APPARATUS_STATUS_CHOICES,
        default='working'
    )
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('handover', 'apparatus')
        ordering = ['handover', 'apparatus']

    def __str__(self):
        return f"{self.apparatus.name}: {self.status}"

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            # Capture previous status for audit
            previous_status = None
            if self.pk:
                prev = ApparatusCondition.objects.filter(pk=self.pk).first()
                previous_status = prev.status if prev else None

            super().save(*args, **kwargs)

            # Update linked equipment status if it changed
            if self.apparatus and getattr(self.apparatus, 'equipment', None):
                equipment = self.apparatus.equipment
                new_status = get_status_by_name(self.status)
                old_equipment_status = equipment.status

                if new_status and (not old_equipment_status or old_equipment_status.name.lower() != new_status.name.lower()):
                    equipment.status = new_status
                    equipment.save(update_fields=['status'])

                    # Audit the equipment status change
                    AuditMixin.create_audit(
                        user=None,
                        action='update',
                        instance=equipment,
                        before={'status': old_equipment_status.name if old_equipment_status else None},
                        after={'status': new_status.name}
                    )

            AuditMixin.create_audit(
                user=None,
                action='update' if previous_status else 'create',
                instance=self,
                before={'status': previous_status} if previous_status else None,
                after={'status': self.status}
            )
