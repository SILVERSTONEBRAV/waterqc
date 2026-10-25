# duty_house/models.py
import uuid

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


class AuditModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="%(class)s_updated",
    )
    class Meta:
        abstract = True


class LocationType(models.TextChoices):
    CAMP = "camp", "Camp"
    BLOCK = "block", "Block"
    WING = "wing", "Wing"
    QUARTERS = "quarters", "Quarters"
    SECTOR = "sector", "Sector"
    CUSTOM = "custom", "Custom"


class Location(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    plant = models.ForeignKey(
        "t.TreatmentPlant",
        on_delete=models.CASCADE,
        related_name="locations",
    )

    name = models.CharField(
        max_length=255,
    )

    code = models.CharField(
        max_length=50,
    )

    location_type = models.CharField(
        max_length=20,
        choices=LocationType.choices,
        default=LocationType.CUSTOM,
        db_index=True,
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    class Meta:
        ordering = ["name"]

        indexes = [
            models.Index(fields=["plant", "code"]),
            models.Index(fields=["location_type"]),
            models.Index(fields=["is_active"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["plant", "code"],
                name="uq_location_plant_code",
            )
        ]

    def __str__(self):
        return self.name


# =========================================================
# DUTY HOUSE
# =========================================================

class DutyHouseStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    MAINTENANCE = "maintenance", "Under Maintenance"
    DECOMMISSIONED = "decommissioned", "Decommissioned"


class DutyHouse(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    plant = models.ForeignKey(
        "t.TreatmentPlant",
        on_delete=models.CASCADE,
        related_name="duty_houses",
    )

    location = models.ForeignKey(
        "duty_house.Location",
        on_delete=models.PROTECT,
        related_name="duty_houses",
    )

    house_number = models.CharField(
        max_length=30,
    )

    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    floors = models.PositiveIntegerField(
        default=1,
    )

    gps_lat = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    gps_lng = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=DutyHouseStatus.choices,
        default=DutyHouseStatus.ACTIVE,
        db_index=True,
    )

    maintenance_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
    )

    critical_issues_open = models.PositiveIntegerField(
        default=0,
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    decommissioned_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["house_number"]

        indexes = [
            models.Index(fields=["plant", "status"]),
            models.Index(fields=["location"]),
            models.Index(fields=["maintenance_score"]),
            models.Index(fields=["is_active"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["plant", "house_number"],
                name="uq_house_number_per_plant",
            )
        ]

    def clean(self):
        super().clean()

        if (
            self.location
            and self.location.plant_id != self.plant_id
        ):
            raise ValidationError(
                {
                    "location":
                    "Location must belong to the selected plant."
                }
            )

    def current_occupancy(self):
        return (
            self.occupancies
            .filter(is_current=True)
            .select_related("user", "unit")
            .first()
        )

    def is_occupied(self):
        return self.current_occupancy() is not None

    def decommission(self):
        self.status = DutyHouseStatus.DECOMMISSIONED
        self.is_active = False
        self.decommissioned_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "is_active",
                "decommissioned_at",
            ]
        )

    def __str__(self):
        return self.name or self.house_number


# =========================================================
# UNIT
# =========================================================

class HousingUnitType(models.TextChoices):
    STUDIO = "studio", "Studio"
    ONE = "1br", "1 Bedroom"
    TWO = "2br", "2 Bedroom"
    THREE = "3br", "3 Bedroom"


class UnitStatus(models.TextChoices):
    VACANT = "vacant", "Vacant"
    OCCUPIED = "occupied", "Occupied"
    MAINTENANCE = "maintenance", "Maintenance"


class DutyHouseUnit(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    duty_house = models.ForeignKey(
        "duty_house.DutyHouse",
        on_delete=models.CASCADE,
        related_name="units",
    )

    unit_number = models.CharField(
        max_length=50,
    )

    unit_type = models.CharField(
        max_length=20,
        choices=HousingUnitType.choices,
    )

    floor = models.PositiveIntegerField(
        default=1,
    )

    status = models.CharField(
        max_length=20,
        choices=UnitStatus.choices,
        default=UnitStatus.VACANT,
        db_index=True,
    )

    max_occupants = models.PositiveIntegerField(
        default=1,
    )

    class Meta:
        ordering = ["unit_number"]

        indexes = [
            models.Index(
                fields=["duty_house", "status"]
            ),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "duty_house",
                    "unit_number",
                ],
                name="uq_unit_number_per_house",
            )
        ]

    @property
    def occupancy_count(self):
        return (
            self.occupancies
            .filter(is_current=True)
            .count()
        )

    @property
    def is_full(self):
        return (
            self.occupancy_count
            >= self.max_occupants
        )

    def __str__(self):
        return (
            f"{self.duty_house} - "
            f"{self.unit_number}"
        )


# =========================================================
# OCCUPANCY
# =========================================================

class OccupancyStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ENDED = "ended", "Ended"


class DutyHouseOccupancy(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    duty_house = models.ForeignKey(
        "duty_house.DutyHouse",
        on_delete=models.CASCADE,
        related_name="occupancies",
    )

    unit = models.ForeignKey(
        "duty_house.DutyHouseUnit",
        on_delete=models.CASCADE,
        related_name="occupancies",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="housing_records",
    )

    status = models.CharField(
        max_length=20,
        choices=OccupancyStatus.choices,
        default=OccupancyStatus.ACTIVE,
    )

    is_current = models.BooleanField(
        default=True,
        db_index=True,
    )

    start_date = models.DateTimeField(
        default=timezone.now,
    )

    end_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    exit_reason = models.TextField(
        null=True,
        blank=True,
    )

    check_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="occupancy_checkins",
    )

    check_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="occupancy_checkouts",
    )

    class Meta:
        ordering = ["-start_date"]

        indexes = [
            models.Index(
                fields=["unit", "is_current"]
            ),
            models.Index(
                fields=["user", "is_current"]
            ),
            models.Index(
                fields=["duty_house", "is_current"]
            ),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(
                    is_current=True
                ),
                name="unique_current_occupancy_per_user",
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.unit
            and self.duty_house
            and self.unit.duty_house_id
            != self.duty_house_id
        ):
            raise ValidationError(
                {
                    "unit":
                    "Unit does not belong to the selected duty house."
                }
            )

        if (
            self.end_date
            and self.end_date < self.start_date
        ):
            raise ValidationError(
                {
                    "end_date":
                    "End date cannot be before start date."
                }
            )

        if self.is_current and self.unit_id:
            unit = self.unit
            current_count = (
                type(self).objects.filter(unit_id=self.unit_id, is_current=True)
                .exclude(pk=self.pk)
                .count()
            )
            if current_count >= unit.max_occupants:
                raise ValidationError(
                    {"unit": "This unit has reached its configured occupant capacity."}
                )

    @transaction.atomic
    def save(self, *args, **kwargs):
        unit = DutyHouseUnit.objects.select_for_update().get(pk=self.unit_id)
        if self.duty_house_id != unit.duty_house_id:
            raise ValidationError("The selected unit does not belong to this duty house.")
        if self.is_current:
            if not unit.duty_house.is_active or unit.duty_house.status == DutyHouseStatus.DECOMMISSIONED:
                raise ValidationError("Occupants cannot be assigned to an inactive house.")
            if unit.status == UnitStatus.MAINTENANCE:
                raise ValidationError("Occupants cannot be assigned to a unit under maintenance.")
            current_count = type(self).objects.filter(
                unit_id=unit.pk, is_current=True
            ).exclude(pk=self.pk).count()
            if current_count >= unit.max_occupants:
                raise ValidationError("This unit has reached its configured occupant capacity.")
        super().save(*args, **kwargs)

        if unit.status != UnitStatus.MAINTENANCE:
            unit.status = (
                UnitStatus.OCCUPIED
                if unit.occupancies.filter(is_current=True).exists()
                else UnitStatus.VACANT
            )
            unit.save(update_fields=["status"])

    def __str__(self):
        return (
            f"{self.user} → "
            f"{self.unit}"
        )


# =========================================================
# OCCUPANCY TRANSFER
# =========================================================

class OccupancyTransfer(AuditModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    from_unit = models.ForeignKey(
        "duty_house.DutyHouseUnit",
        on_delete=models.CASCADE,
        related_name="transfers_from",
    )

    to_unit = models.ForeignKey(
        "duty_house.DutyHouseUnit",
        on_delete=models.CASCADE,
        related_name="transfers_to",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    transferred_at = models.DateTimeField(
        auto_now_add=True,
    )

    transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="occupancy_transfers",
    )

    @transaction.atomic
    def execute(self, executor):
        DutyHouseOccupancy = apps.get_model(
            "duty_house",
            "DutyHouseOccupancy",
        )

        try:
            current = (
                DutyHouseOccupancy.objects
                .select_for_update()
                .get(
                    unit=self.from_unit,
                    user=self.user,
                    is_current=True,
                )
            )
        except DutyHouseOccupancy.DoesNotExist as exc:
            raise ValidationError("This housing assignment is no longer current.") from exc

        if self.from_unit_id == self.to_unit_id:
            raise ValidationError("Choose a different destination unit.")
        if self.from_unit.duty_house.plant_id != self.to_unit.duty_house.plant_id:
            raise ValidationError("Transfers must stay within the same treatment plant.")
        if (
            not self.to_unit.duty_house.is_active
            or self.to_unit.duty_house.status != DutyHouseStatus.ACTIVE
        ):
            raise ValidationError("The destination house is not available for occupancy.")
        if self.to_unit.status == UnitStatus.MAINTENANCE:
            raise ValidationError("The destination unit is under maintenance.")
        if self.to_unit.occupancies.filter(is_current=True).count() >= self.to_unit.max_occupants:
            raise ValidationError("The destination unit has reached capacity.")

        current.is_current = False
        current.status = (
            OccupancyStatus.ENDED
        )
        current.end_date = timezone.now()
        current.check_out_by = executor
        current.updated_by = executor

        current.save(
            update_fields=[
                "is_current",
                "status",
                "end_date",
                "check_out_by",
                "updated_by",
                "updated_at",
            ]
        )

        DutyHouseOccupancy.objects.create(
            duty_house=self.to_unit.duty_house,
            unit=self.to_unit,
            user=self.user,
            status=OccupancyStatus.ACTIVE,
            is_current=True,
            check_in_by=executor,
            created_by=executor,
            updated_by=executor,
        )

        self.transferred_by = executor
        self.updated_by = executor

        self.save(
            update_fields=[
                "transferred_by",
                "updated_by",
                "updated_at",
            ]
        )

    def __str__(self):
        return (
            f"{self.user}: "
            f"{self.from_unit} → "
            f"{self.to_unit}"
        )
