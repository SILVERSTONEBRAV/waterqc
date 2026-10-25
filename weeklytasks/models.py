from __future__ import annotations

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import Section
from sc.models import Shift, ShiftAssignment, ShiftSectionRequirement
from t.models import TreatmentPlant


User = settings.AUTH_USER_MODEL


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class StandardWeeklyTask(TimestampedModel):
    code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
    )
    name = models.CharField(
        max_length=255,
        db_index=True,
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    class Meta:
        ordering = ["code", "name"]
        indexes = [
            models.Index(
                fields=["is_active", "code"],
                name="swt_active_code_idx",
            ),
            models.Index(
                fields=["is_active", "name"],
                name="swt_active_name_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class MonthlyDutySchedule(TimestampedModel):
    month = models.PositiveSmallIntegerField(
        choices=[(month, month) for month in range(1, 13)],
        db_index=True,
    )
    year = models.PositiveIntegerField(
        db_index=True,
    )
    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.CASCADE,
        related_name="monthly_duty_schedules",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="monthly_duty_schedules",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_monthly_duty_schedules",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = [
            "-year",
            "-month",
            "treatment_plant",
            "section",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "month",
                    "year",
                    "treatment_plant",
                    "section",
                ],
                name="unique_monthly_schedule_plant_section",
            ),
            models.CheckConstraint(
                condition=Q(month__gte=1) & Q(month__lte=12),
                name="monthly_schedule_valid_month",
            ),
            models.CheckConstraint(
                condition=Q(year__gte=2000),
                name="monthly_schedule_valid_year",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "treatment_plant",
                    "section",
                    "-year",
                    "-month",
                ],
                name="mds_plant_section_idx",
            ),
            models.Index(
                fields=[
                    "section",
                    "-year",
                    "-month",
                ],
                name="mds_section_date_idx",
            ),
            models.Index(
                fields=[
                    "year",
                    "month",
                ],
                name="mds_date_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.month}/{self.year} - "
            f"{self.treatment_plant.name} - "
            f"{self.section.name}"
        )

    @property
    def month_start(self) -> date:
        return date(
            self.year,
            self.month,
            1,
        )

    @property
    def month_end(self) -> date:
        if self.month == 12:
            return date(
                self.year,
                12,
                31,
            )

        return date(
            self.year,
            self.month + 1,
            1,
        ).replace(day=1) - date.resolution

    def get_scheduled_sections(self):
        if not self.section_id:
            return Section.objects.none()

        return Section.objects.filter(
            pk=self.section_id,
        )

    def get_scheduled_sections_names(self):
        if not self.section_id:
            return []

        return [self.section.name]

    def get_assigned_users(self):
        return (
            User.objects.filter(
                shift_assignments__date__year=self.year,
                shift_assignments__date__month=self.month,
                shift_assignments__is_deleted=False,
                assigned_treatment_plant_id=self.treatment_plant_id,
                section_id=self.section_id,
                is_active=True,
            )
            .distinct()
            .order_by(
                "last_name",
                "first_name",
                "username",
            )
        )

    def get_available_shifts(self):
        if not self.treatment_plant_id or not self.section_id:
            return Shift.objects.none()

        return (
            Shift.objects.filter(
                treatment_plant_id=self.treatment_plant_id,
                is_deleted=False,
                section_requirements__section_id=self.section_id,
            )
            .distinct()
            .order_by(
                "start_time",
                "name",
            )
        )

    def clean(self):
        super().clean()

        errors = {}

        if not self.treatment_plant_id:
            errors["treatment_plant"] = (
                "A treatment plant is required."
            )

        if not self.section_id:
            errors["section"] = (
                "A section is required."
            )

        if self.year is not None and self.year < 2000:
            errors["year"] = (
                "The schedule year must be 2000 or later."
            )

        if self.section_id and self.treatment_plant_id:
            sec_plant_id = getattr(self.section, "treatment_plant_id", None)
            if sec_plant_id and sec_plant_id != self.treatment_plant_id:
                errors["section"] = (
                    f"Section '{self.section.name}' belongs to plant '{self.section.treatment_plant.name}', "
                    f"which does not match schedule treatment plant '{self.treatment_plant.name}'."
                )

            section_users_exist = User.objects.filter(
                section_id=self.section_id,
                assigned_treatment_plant_id=self.treatment_plant_id,
                is_active=True,
            ).exists()

            if not section_users_exist:
                errors["section"] = (
                    "The selected section has no active users "
                    "assigned to this treatment plant."
                )

        if errors:
            raise ValidationError(errors)


class DutyWeek(TimestampedModel):
    schedule = models.ForeignKey(
        MonthlyDutySchedule,
        on_delete=models.CASCADE,
        related_name="weeks",
    )
    start_date = models.DateField(
        db_index=True,
    )
    end_date = models.DateField(
        db_index=True,
    )

    class Meta:
        ordering = [
            "start_date",
            "end_date",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "schedule",
                    "start_date",
                    "end_date",
                ],
                name="unique_duty_week_per_schedule",
            ),
            models.CheckConstraint(
                condition=Q(
                    end_date__gte=models.F("start_date"),
                ),
                name="duty_week_end_after_start",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "schedule",
                    "start_date",
                    "end_date",
                ],
                name="duty_week_schedule_dates_idx",
            ),
            models.Index(
                fields=[
                    "start_date",
                    "end_date",
                ],
                name="duty_week_date_range_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.schedule.section.name}: "
            f"{self.start_date} → {self.end_date}"
        )

    @property
    def treatment_plant(self):
        return self.schedule.treatment_plant

    @property
    def treatment_plant_id(self):
        return self.schedule.treatment_plant_id

    @property
    def section(self):
        return self.schedule.section

    @property
    def section_id(self):
        return self.schedule.section_id

    def clean(self):
        super().clean()

        errors = {}

        if not self.schedule_id:
            errors["schedule"] = (
                "A monthly duty schedule is required."
            )

        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                errors["end_date"] = (
                    "The end date cannot be earlier than "
                    "the start date."
                )

        if self.schedule_id and self.start_date and self.end_date:
            schedule = self.schedule

            if self.start_date < schedule.month_start:
                errors["start_date"] = (
                    "The week start date cannot be earlier than "
                    "the monthly schedule start date."
                )

            if self.end_date > schedule.month_end:
                errors["end_date"] = (
                    "The week end date cannot be later than "
                    "the monthly schedule end date."
                )

        if errors:
            raise ValidationError(errors)


class WeeklyDutyTask(TimestampedModel):
    week = models.ForeignKey(
        DutyWeek,
        on_delete=models.CASCADE,
        related_name="weekly_tasks",
    )
    task_template = models.ForeignKey(
        StandardWeeklyTask,
        on_delete=models.PROTECT,
        related_name="weekly_duty_tasks",
    )
    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.CASCADE,
        related_name="weekly_duty_tasks",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="weekly_duty_tasks",
    )

    class Meta:
        ordering = [
            "week__start_date",
            "section",
            "task_template__code",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "week",
                    "task_template",
                    "treatment_plant",
                    "section",
                ],
                name="unique_weekly_task_plant_section",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "week",
                    "treatment_plant",
                    "section",
                ],
                name="wdt_week_plant_section_idx",
            ),
            models.Index(
                fields=[
                    "treatment_plant",
                    "section",
                    "week",
                ],
                name="wdt_plant_section_week_idx",
            ),
            models.Index(
                fields=[
                    "section",
                    "week",
                ],
                name="wdt_section_week_idx",
            ),
            models.Index(
                fields=[
                    "task_template",
                    "week",
                ],
                name="wdt_template_week_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.task_template.name} "
            f"({self.week}) | "
            f"{self.treatment_plant.name} | "
            f"{self.section.name}"
        )

    @property
    def start_date(self):
        return self.week.start_date

    @property
    def end_date(self):
        return self.week.end_date

    def get_daily_assignments(self):
        return (
            self.daily_assignments
            .select_related(
                "user",
                "user__section",
                "shift",
                "task",
                "task__task_template",
                "task__section",
                "task__treatment_plant",
            )
            .order_by(
                "date",
                "shift__start_time",
                "user__last_name",
                "user__first_name",
            )
        )

    def get_assigned_users(self):
        return (
            User.objects.filter(
                daily_assignments__task=self,
                assigned_treatment_plant_id=self.treatment_plant_id,
                section_id=self.section_id,
                is_active=True,
            )
            .distinct()
            .order_by(
                "last_name",
                "first_name",
                "username",
            )
        )

    def get_assigned_sections(self):
        if not self.section_id:
            return Section.objects.none()

        return Section.objects.filter(
            pk=self.section_id,
        )

    def get_assigned_sections_names(self):
        if not self.section_id:
            return []

        return [self.section.name]

    def get_available_shifts(self):
        if not self.treatment_plant_id or not self.section_id:
            return Shift.objects.none()

        return (
            Shift.objects.filter(
                treatment_plant_id=self.treatment_plant_id,
                is_deleted=False,
                section_requirements__section_id=self.section_id,
            )
            .distinct()
            .order_by(
                "start_time",
                "name",
            )
        )

    def get_available_users(self, assignment_date=None):
        queryset = User.objects.filter(
            assigned_treatment_plant_id=self.treatment_plant_id,
            section_id=self.section_id,
            is_active=True,
        )

        if assignment_date is not None:
            queryset = queryset.filter(
                shift_assignments__date=assignment_date,
                shift_assignments__is_deleted=False,
            )

        return (
            queryset
            .distinct()
            .order_by(
                "last_name",
                "first_name",
                "username",
            )
        )

    def clean(self):
        super().clean()

        errors = {}

        if not self.week_id:
            errors["week"] = (
                "A duty week is required."
            )

        if not self.task_template_id:
            errors["task_template"] = (
                "A task template is required."
            )

        if not self.treatment_plant_id:
            errors["treatment_plant"] = (
                "A treatment plant is required."
            )

        if not self.section_id:
            errors["section"] = (
                "A section is required."
            )
        elif self.treatment_plant_id:
            sec_plant_id = getattr(self.section, "treatment_plant_id", None)
            if sec_plant_id and sec_plant_id != self.treatment_plant_id:
                errors["section"] = (
                    f"Section '{self.section.name}' belongs to plant '{self.section.treatment_plant.name}', "
                    f"which does not match task treatment plant '{self.treatment_plant.name}'."
                )

        if self.task_template_id and not self.task_template.is_active:
            errors["task_template"] = (
                "An inactive task template cannot be assigned "
                "to a weekly duty task."
            )

        if self.week_id:
            week = self.week

            if (
                self.treatment_plant_id
                and week.schedule.treatment_plant_id
                != self.treatment_plant_id
            ):
                errors["treatment_plant"] = (
                    "The task treatment plant must match "
                    "the weekly schedule treatment plant."
                )

            if (
                self.section_id
                and week.schedule.section_id
                != self.section_id
            ):
                errors["section"] = (
                    "The task section must match "
                    "the weekly schedule section."
                )

        if errors:
            raise ValidationError(errors)


class DailyTaskAssignment(TimestampedModel):
    task = models.ForeignKey(
        WeeklyDutyTask,
        on_delete=models.CASCADE,
        related_name="daily_assignments",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="daily_assignments",
    )
    date = models.DateField(
        db_index=True,
    )
    shift = models.ForeignKey(
        Shift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="weekly_task_assignments",
    )
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = [
            "date",
            "shift__start_time",
            "user__last_name",
            "user__first_name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "task",
                    "user",
                    "date",
                ],
                name="unique_daily_task_user_date",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "task",
                    "date",
                ],
                name="dta_task_date_idx",
            ),
            models.Index(
                fields=[
                    "user",
                    "date",
                ],
                name="dta_user_date_idx",
            ),
            models.Index(
                fields=[
                    "date",
                    "shift",
                ],
                name="dta_date_shift_idx",
            ),
            models.Index(
                fields=[
                    "user",
                    "task",
                ],
                name="dta_user_task_idx",
            ),
        ]

    def __str__(self) -> str:
        section = getattr(
            self.user,
            "section",
            None,
        )

        section_name = (
            section.name
            if section
            else "No Section"
        )

        return (
            f"{self.user.get_full_name()} "
            f"({section_name}) on {self.date} "
            f"for {self.task.task_template.name}"
        )

    @property
    def treatment_plant(self):
        return self.task.treatment_plant

    @property
    def treatment_plant_id(self):
        return self.task.treatment_plant_id

    @property
    def section(self):
        return self.task.section

    @property
    def section_id(self):
        return self.task.section_id

    def get_valid_shifts(self):
        if not self.task_id or not self.user_id or not self.date:
            return Shift.objects.none()

        return (
            Shift.objects.filter(
                treatment_plant_id=self.task.treatment_plant_id,
                is_deleted=False,
                section_requirements__section_id=self.task.section_id,
                assignments__staff_id=self.user_id,
                assignments__date=self.date,
                assignments__is_deleted=False,
            )
            .distinct()
            .order_by(
                "start_time",
                "name",
            )
        )

    def clean(self):
        super().clean()

        errors = {}

        if not self.task_id:
            errors["task"] = (
                "A weekly duty task is required."
            )

        if not self.user_id:
            errors["user"] = (
                "A user is required."
            )

        if self.task_id and self.date:
            task = self.task

            if (
                self.date < task.start_date
                or self.date > task.end_date
            ):
                errors["date"] = (
                    "The assignment date must fall within "
                    "the weekly task date range."
                )

        if self.task_id and self.user_id:
            task = self.task
            user = self.user

            if (
                user.assigned_treatment_plant_id
                != task.treatment_plant_id
            ):
                errors["user"] = (
                    "The assigned user must belong to "
                    "the same treatment plant as the task."
                )

            if (
                getattr(user, "section_id", None)
                != task.section_id
            ):
                errors["user"] = (
                    "The assigned user must belong to "
                    "the same section as the task."
                )

            if not user.is_active:
                errors["user"] = (
                    "An inactive user cannot be assigned "
                    "to a weekly duty task."
                )

        if self.shift_id and self.task_id:
            task = self.task
            shift = self.shift

            if shift.is_deleted:
                errors["shift"] = (
                    "A deleted shift cannot be used "
                    "for a weekly task assignment."
                )

            if (
                shift.treatment_plant_id
                != task.treatment_plant_id
            ):
                errors["shift"] = (
                    "The selected shift must belong to "
                    "the same treatment plant as the task."
                )

            requirement_exists = (
                ShiftSectionRequirement.objects.filter(
                    shift_id=shift.pk,
                    section_id=task.section_id,
                ).exists()
            )

            if not requirement_exists:
                errors["shift"] = (
                    "The selected shift is not configured "
                    "for the task's section."
                )

        if (
            self.shift_id
            and self.user_id
            and self.date
            and not errors.get("shift")
        ):
            assigned = ShiftAssignment.objects.filter(
                staff_id=self.user_id,
                shift_id=self.shift_id,
                date=self.date,
                is_deleted=False,
            ).exists()

            if not assigned:
                errors["shift"] = (
                    f"{self.user.get_full_name()} is not assigned "
                    f"to this shift on {self.date}."
                )

        if errors:
            raise ValidationError(errors)
