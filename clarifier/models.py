from __future__ import annotations

import math
import string
import random
from decimal import Decimal

from django.db import models
from django.db.models import (
    Q,
    Avg,
    Max,
    Min,
    Sum,
    Count,
)
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from accounts.models import CustomUser
from t.models import (
    TreatmentPlant,
    TreatmentPlantPhase,
)

User = CustomUser


# ============================================================
# CONSTANTS
# ============================================================

MAX_DIGITS = 12
DECIMAL_PLACES = 3


def generate_uuid(length=8):
    return "".join(
        random.choices(
            string.ascii_uppercase + string.digits,
            k=length,
        )
    )


# ============================================================
# ABSTRACT BASE
# ============================================================

class TimeStampedModel(models.Model):

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        abstract = True


# ============================================================
# ENUMS
# ============================================================

class ClarifierStatus(models.TextChoices):

    ONLINE = "online", _("Online")

    STANDBY = "standby", _("Standby")

    MAINTENANCE = "maintenance", _("Maintenance")

    ISOLATED = "isolated", _("Isolated")

    OUT_OF_SERVICE = (
        "out_of_service",
        _("Out of Service"),
    )

    FAULT = "fault", _("Fault")


class ClarifierDesign(models.TextChoices):

    RECTANGULAR = (
        "rectangular",
        _("Rectangular"),
    )

    CIRCULAR = (
        "circular",
        _("Circular"),
    )


class ClarifierFlowPattern(models.TextChoices):

    HORIZONTAL = (
        "horizontal",
        _("Horizontal"),
    )

    VERTICAL = (
        "vertical",
        _("Vertical"),
    )


class ScraperType(models.TextChoices):

    BRIDGE = "bridge", _("Bridge")

    SUCTION = "suction", _("Suction")

    CHAIN = "chain", _("Chain")

    ROTARY = "rotary", _("Rotary")


class ClarifierPriority(models.TextChoices):

    LOW = "low", _("Low")

    NORMAL = "normal", _("Normal")

    HIGH = "high", _("High")

    CRITICAL = "critical", _("Critical")


# ============================================================
# QUERYSET
# ============================================================

class ClarifierQuerySet(models.QuerySet):

    def active(self):
        return self.filter(active=True)

    def online(self):
        return self.filter(
            status=ClarifierStatus.ONLINE
        )

    def maintenance(self):
        return self.filter(
            status=ClarifierStatus.MAINTENANCE
        )

    def isolated(self):
        return self.filter(
            status=ClarifierStatus.ISOLATED
        )

    def overdue(self):

        today = timezone.localdate()

        return self.filter(
            next_maintenance_date__lt=today
        )

    def by_plant(self, plant):

        return self.filter(
            treatment_plant=plant
        )


# ============================================================
# MANAGER
# ============================================================

class ClarifierManager(models.Manager):

    def get_queryset(self):
        return ClarifierQuerySet(
            self.model,
            using=self._db,
        )

    def active(self):
        return self.get_queryset().active()

    def online(self):
        return self.get_queryset().online()

    def overdue(self):
        return self.get_queryset().overdue()

    def maintenance(self):
        return self.get_queryset().maintenance()


# ============================================================
# CLARIFIER
# ============================================================

class Clarifier(TimeStampedModel):

    uuid = models.CharField(
        max_length=8,
        unique=True,
        editable=False,
        default=generate_uuid,
        db_index=True,
    )

    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.CASCADE,
        related_name="clarifiers",
        db_index=True,
    )

    phase = models.ForeignKey(
        TreatmentPlantPhase,
        on_delete=models.PROTECT,
        related_name="clarifiers",
        null=True,
        blank=True,
    )

    name = models.CharField(
        max_length=100,
    )

    asset_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
    )

    manufacturer = models.CharField(
        max_length=255,
        blank=True,
    )

    model = models.CharField(
        max_length=255,
        blank=True,
    )

    serial_number = models.CharField(
        max_length=255,
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=ClarifierStatus.choices,
        default=ClarifierStatus.ONLINE,
        db_index=True,
    )

    priority = models.CharField(
        max_length=20,
        choices=ClarifierPriority.choices,
        default=ClarifierPriority.NORMAL,
    )

    design = models.CharField(
        max_length=30,
        choices=ClarifierDesign.choices,
    )

    flow_pattern = models.CharField(
        max_length=30,
        choices=ClarifierFlowPattern.choices,
    )

    scraper_type = models.CharField(
        max_length=30,
        choices=ScraperType.choices,
        default=ScraperType.BRIDGE,
    )

    installation_date = models.DateField()

    commissioning_date = models.DateField(
        null=True,
        blank=True,
    )

    expected_service_life = models.PositiveIntegerField(
        default=25,
        help_text=_("Years"),
    )

    active = models.BooleanField(
        default=True,
        db_index=True,
    )

    design_capacity = models.DecimalField(
        max_digits=MAX_DIGITS,
        decimal_places=DECIMAL_PLACES,
        help_text="m³/hr",
    )

    operating_capacity = models.DecimalField(
        max_digits=MAX_DIGITS,
        decimal_places=DECIMAL_PLACES,
        default=0,
        help_text="m³/hr",
    )

    peak_capacity = models.DecimalField(
        max_digits=MAX_DIGITS,
        decimal_places=DECIMAL_PLACES,
        default=0,
        help_text="m³/hr",
    )

    average_flow = models.DecimalField(
        max_digits=MAX_DIGITS,
        decimal_places=DECIMAL_PLACES,
        default=0,
    )

    current_flow = models.DecimalField(
        max_digits=MAX_DIGITS,
        decimal_places=DECIMAL_PLACES,
        default=0,
    )

    detention_time = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=2,
        help_text="Hours",
    )

    surface_area = models.DecimalField(
        max_digits=MAX_DIGITS,
        decimal_places=DECIMAL_PLACES,
        default=0,
        help_text="Square metres",
    )

    surface_loading_rate = models.DecimalField(
        max_digits=MAX_DIGITS,
        decimal_places=DECIMAL_PLACES,
        default=0,
        help_text="m³/m²/hr",
    )

    volume = models.DecimalField(
        max_digits=MAX_DIGITS,
        decimal_places=DECIMAL_PLACES,
        default=0,
        editable=False,
    )

    water_depth = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=0,
    )

    freeboard = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=0,
    )

    sludge_blanket_depth = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=0,
    )

    diameter = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
    )

    length = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
    )

    width = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
    )

    side_water_depth = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=0,
    )

    bottom_slope = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=0,
    )

    objects = ClarifierManager()

    def __str__(self):
        return (
            f"{self.treatment_plant.code} - "
            f"{self.name}"
        )
    # ============================================================
    # MAINTENANCE
    # ============================================================

    last_maintenance_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
    )

    next_maintenance_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
    )

    maintenance_interval_days = models.PositiveIntegerField(
        default=180,
    )

    last_inspection_date = models.DateField(
        null=True,
        blank=True,
    )

    next_inspection_date = models.DateField(
        null=True,
        blank=True,
    )

    # ============================================================
    # OPERATION
    # ============================================================

    operating_hours = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    runtime_today = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )

    total_flow_processed = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        default=0,
        help_text="m³",
    )

    sludge_removed_today = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
    )

    sludge_removed_total = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        default=0,
    )

    desludging_interval_hours = models.PositiveIntegerField(
        default=8,
    )

    scraper_speed = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="m/min",
    )

    bridge_speed = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )

    torque = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )

    # ============================================================
    # ENERGY
    # ============================================================

    motor_power = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="kW",
    )

    voltage = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )

    current = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )

    power_factor = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
    )

    energy_today = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
    )

    energy_total = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        default=0,
    )

    # ============================================================
    # SCADA
    # ============================================================

    plc_tag = models.CharField(
        max_length=100,
        blank=True,
    )

    scada_tag = models.CharField(
        max_length=100,
        blank=True,
    )

    remote_enabled = models.BooleanField(
        default=False,
    )

    auto_mode = models.BooleanField(
        default=True,
    )

    communication_ok = models.BooleanField(
        default=True,
    )

    last_scada_sync = models.DateTimeField(
        null=True,
        blank=True,
    )

    # ============================================================
    # DOCUMENTATION
    # ============================================================

    remarks = models.TextField(
        blank=True,
    )

    class Meta:

        ordering = [
            "treatment_plant",
            "name",
        ]

        verbose_name = "Clarifier"

        verbose_name_plural = "Clarifiers"

        constraints = [

            models.UniqueConstraint(
                fields=[
                    "treatment_plant",
                    "name",
                ],
                name="uq_clarifier_name",
            ),

            models.CheckConstraint(
                check=Q(
                    design_capacity__gt=0
                ),
                name="clarifier_design_capacity_positive",
            ),

            models.CheckConstraint(
                check=Q(
                    operating_capacity__gte=0
                ),
                name="clarifier_operating_capacity_positive",
            ),

            models.CheckConstraint(
                check=Q(
                    water_depth__gt=0
                ),
                name="clarifier_depth_positive",
            ),

        ]

        indexes = [

            models.Index(
                fields=[
                    "status",
                ]
            ),

            models.Index(
                fields=[
                    "active",
                ]
            ),

            models.Index(
                fields=[
                    "next_maintenance_date",
                ]
            ),

            models.Index(
                fields=[
                    "priority",
                ]
            ),

            models.Index(
                fields=[
                    "treatment_plant",
                    "status",
                ]
            ),

        ]

    # ============================================================
    # PROPERTIES
    # ============================================================

    @property
    def age_years(self):

        return (
            timezone.localdate()
            - self.installation_date
        ).days // 365

    @property
    def utilization_percent(self):

        if self.design_capacity == 0:
            return Decimal("0")

        return round(
            (
                self.current_flow
                /
                self.design_capacity
            ) * 100,
            2,
        )

    @property
    def requires_maintenance(self):

        if not self.next_maintenance_date:
            return False

        return (
            timezone.localdate()
            >= self.next_maintenance_date
        )

    @property
    def is_overloaded(self):

        return (
            self.current_flow >
            self.design_capacity
        )

    @property
    def remaining_service_years(self):

        return max(
            0,
            self.expected_service_life
            - self.age_years
        )

    # ============================================================
    # CALCULATIONS
    # ============================================================

    def calculate_volume(self):

        if (
            self.design
            ==
            ClarifierDesign.CIRCULAR
        ):

            radius = self.diameter / Decimal("2")

            self.volume = Decimal(str(math.pi)) \
                * radius \
                * radius \
                * self.water_depth

        else:

            self.volume = (
                self.length
                * self.width
                * self.water_depth
            )

    def calculate_surface_area(self):

        if (
            self.design
            ==
            ClarifierDesign.CIRCULAR
        ):

            radius = self.diameter / Decimal("2")

            self.surface_area = (
                Decimal(str(math.pi))
                * radius
                * radius
            )

        else:

            self.surface_area = (
                self.length
                * self.width
            )

    def calculate_surface_loading(self):

        if self.surface_area:

            self.surface_loading_rate = (
                self.current_flow
                /
                self.surface_area
            )

    # ============================================================
    # VALIDATION
    # ============================================================

    def clean(self):

        super().clean()

        if self.design == ClarifierDesign.CIRCULAR:

            if not self.diameter:
                raise ValidationError(
                    {
                        "diameter":
                        "Circular clarifiers require a diameter."
                    }
                )

            if self.length or self.width:
                raise ValidationError(
                    "Length and width must be empty."
                )

        else:

            if self.diameter:
                raise ValidationError(
                    "Diameter is not applicable."
                )

            if not self.length:
                raise ValidationError(
                    {
                        "length":
                        "Length is required."
                    }
                )

            if not self.width:
                raise ValidationError(
                    {
                        "width":
                        "Width is required."
                    }
                )

    # ============================================================
    # SAVE
    # ============================================================

    def save(self, *args, **kwargs):

        self.full_clean()

        self.calculate_volume()

        self.calculate_surface_area()

        self.calculate_surface_loading()

        super().save(*args, **kwargs)
# ============================================================
# VALVE ENUMS
# ============================================================

class ValveType(models.TextChoices):
    INLET = "inlet", _("Inlet")
    OUTLET = "outlet", _("Outlet")
    DESLUDGE = "desludge", _("Desludge")
    DRAIN = "drain", _("Drain")
    OVERFLOW = "overflow", _("Overflow")
    BYPASS = "bypass", _("Bypass")
    ISOLATION = "isolation", _("Isolation")
    WASHOUT = "washout", _("Washout")


class ValveStatus(models.TextChoices):
    OPEN = "open", _("Open")
    CLOSED = "closed", _("Closed")
    PARTIALLY_OPEN = "partial", _("Partially Open")
    FAULT = "fault", _("Fault")
    MAINTENANCE = "maintenance", _("Maintenance")
    LOCKED = "locked", _("Locked")


class ValveActuator(models.TextChoices):
    MANUAL = "manual", _("Manual")
    ELECTRIC = "electric", _("Electric")
    PNEUMATIC = "pneumatic", _("Pneumatic")
    HYDRAULIC = "hydraulic", _("Hydraulic")


# ============================================================
# CLARIFIER VALVE
# ============================================================

class ClarifierValve(TimeStampedModel):

    uuid = models.CharField(
        max_length=8,
        unique=True,
        default=generate_uuid,
        editable=False,
        db_index=True,
    )

    clarifier = models.ForeignKey(
        Clarifier,
        on_delete=models.CASCADE,
        related_name="valves",
        db_index=True,
    )

    valve_number = models.CharField(
        max_length=30,
    )

    name = models.CharField(
        max_length=100,
    )

    valve_type = models.CharField(
        max_length=20,
        choices=ValveType.choices,
        db_index=True,
    )

    actuator = models.CharField(
        max_length=20,
        choices=ValveActuator.choices,
        default=ValveActuator.MANUAL,
    )

    status = models.CharField(
        max_length=20,
        choices=ValveStatus.choices,
        default=ValveStatus.CLOSED,
        db_index=True,
    )

    manufacturer = models.CharField(
        max_length=150,
        blank=True,
    )

    model = models.CharField(
        max_length=150,
        blank=True,
    )

    serial_number = models.CharField(
        max_length=150,
        blank=True,
    )

    diameter = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="mm",
    )

    pressure_rating = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Bar",
    )

    flow_coefficient = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=0,
        help_text="Cv",
    )

    opening_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    normally_open = models.BooleanField(
        default=False,
    )

    automatic = models.BooleanField(
        default=False,
    )

    installation_date = models.DateField(
        null=True,
        blank=True,
    )

    commissioning_date = models.DateField(
        null=True,
        blank=True,
    )

    last_operated = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_service = models.DateField(
        null=True,
        blank=True,
    )

    next_service = models.DateField(
        null=True,
        blank=True,
        db_index=True,
    )

    operation_count = models.PositiveBigIntegerField(
        default=0,
    )

    plc_tag = models.CharField(
        max_length=100,
        blank=True,
    )

    scada_tag = models.CharField(
        max_length=100,
        blank=True,
    )

    communication_ok = models.BooleanField(
        default=True,
    )

    remote_enabled = models.BooleanField(
        default=False,
    )

    remarks = models.TextField(
        blank=True,
    )

    active = models.BooleanField(
        default=True,
        db_index=True,
    )

    class Meta:

        ordering = [
            "clarifier",
            "valve_number",
        ]

        verbose_name = "Clarifier Valve"

        verbose_name_plural = "Clarifier Valves"

        constraints = [

            models.UniqueConstraint(
                fields=[
                    "clarifier",
                    "valve_number",
                ],
                name="uq_clarifier_valve_number",
            ),

            models.CheckConstraint(
                check=Q(
                    diameter__gt=0
                ),
                name="clarifier_valve_positive_diameter",
            ),

            models.CheckConstraint(
                check=Q(
                    opening_percent__gte=0
                ) &
                Q(
                    opening_percent__lte=100
                ),
                name="clarifier_valve_opening_range",
            ),
        ]

        indexes = [

            models.Index(
                fields=["status"],
            ),

            models.Index(
                fields=["valve_type"],
            ),

            models.Index(
                fields=["active"],
            ),

            models.Index(
                fields=[
                    "clarifier",
                    "status",
                ],
            ),
        ]

    def __str__(self):
        return (
            f"{self.clarifier.name} "
            f"- {self.valve_number}"
        )

    @property
    def requires_service(self):

        if not self.next_service:
            return False

        return timezone.localdate() >= self.next_service

    @property
    def is_open(self):
        return self.status == ValveStatus.OPEN

    @property
    def is_closed(self):
        return self.status == ValveStatus.CLOSED

    def clean(self):

        super().clean()

        if self.automatic and self.actuator == ValveActuator.MANUAL:
            raise ValidationError(
                "Automatic valves cannot use a manual actuator."
            )

    def save(self, *args, **kwargs):

        self.full_clean()

        super().save(*args, **kwargs)
ClarifierValve.objects.filter(pk=self.valve_id).update(
    last_operated=self.created_at,
    operation_count=F("operation_count") + 1,
    opening_percent=self.opening_after,
)