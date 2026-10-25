#t/models.py
import string
import random
from datetime import date, timedelta
from django.db import models
from django.core.exceptions import ValidationError
from parameters.models import PhysicochemicalParameter, MicrobialParameter, HeavyMetalParameter


def generate_uuid():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


class TreatmentPlant(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True)  # e.g., KSM, NRB, THK
    location = models.CharField(max_length=200)  # Simplified from GIS PointField

    def __str__(self):
        return f"{self.code} - {self.name}"



class TreatmentPlantPhase(models.Model):
    name = models.CharField(max_length=100)
    treatment_plant = models.ForeignKey(TreatmentPlant, related_name='phases', on_delete=models.CASCADE)
    design_capacity = models.FloatField(help_text="Design capacity in cubic meters per hour")
    operational_capacity = models.FloatField(help_text="Operational capacity in cubic meters per hour")

    def __str__(self):
        return f"{self.name} - {self.treatment_plant.name}"


# ========================
# Filter System
# ========================
class FilterType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class WaterFilter(models.Model):
    STATUS_CHOICES = [
        ('working', 'Working'),
        ('backwashing', 'Backwashing'),
        ('isolated', 'Isolated'),
        ('maintenance', 'Maintenance'),
    ]

    name = models.CharField(max_length=100)
    filter_type = models.ForeignKey(FilterType, on_delete=models.CASCADE, related_name='water_filters')
    installation_date = models.DateField()
    last_maintenance_date = models.DateField()
    location = models.CharField(max_length=200)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES)
    design_capacity = models.FloatField(help_text="Design capacity in m³/hr")
    flow_rate = models.FloatField(help_text="Current flow rate in m³/hr")
    depth = models.FloatField(help_text="Depth in meters")
    length = models.FloatField(help_text="Length in meters")
    width = models.FloatField(help_text="Width in meters")
    volume = models.FloatField(blank=True, null=True, help_text="Volume in m³", editable=False)
    treatment_plant = models.ForeignKey(TreatmentPlant, on_delete=models.CASCADE, related_name='filters', null=True, blank=True)
    phase = models.ForeignKey(TreatmentPlantPhase, on_delete=models.CASCADE, related_name='filters', null=True, blank=True)

    def __str__(self):
        return self.name

    @property
    def age(self):
        return (date.today() - self.installation_date).days // 365

    def needs_maintenance(self):
        return (date.today() - self.last_maintenance_date) >= timedelta(days=180)

    def calculate_volume(self):
        self.volume = self.length * self.width * self.depth

    def save(self, *args, **kwargs):
        self.calculate_volume()
        super().save(*args, **kwargs)


# ========================
# Shared Status Model
# ========================
class Status(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "Statuses"

    def __str__(self):
        return self.name


# ========================
# Clarifier and Valves
# ========================
class Clarifier(models.Model):
    FLOW_TYPE_CHOICES = [
        ('vertical', 'Vertical Flow'),
        ('horizontal', 'Horizontal Flow'),
    ]
    DESIGN_CHOICES = [
        ('cuboid', 'Cuboid'),
        ('cylindrical', 'Cylindrical'),
    ]

    name = models.CharField(max_length=100)
    design_capacity = models.FloatField(help_text="Design capacity in m³/hr", default=10)
    installation_date = models.DateField()
    last_maintenance_date = models.DateField()
    treatment_plant = models.ForeignKey(TreatmentPlant, on_delete=models.CASCADE, related_name='clarifiers')
    phase = models.ForeignKey(TreatmentPlantPhase, on_delete=models.CASCADE, related_name='clarifiers', null=True, blank=True)
    clarifier_capacity = models.FloatField(help_text="Clarifier capacity in m³", default=10)
    surface_area = models.FloatField(help_text="Surface area in m²", default=10000)
    surface_loading = models.FloatField(help_text="Surface loading rate in m³/m²/hr", default=10000)
    flow_type = models.CharField(max_length=50, choices=FLOW_TYPE_CHOICES, default='vertical')
    design = models.CharField(max_length=50, choices=DESIGN_CHOICES, default='cuboid')
    depth = models.FloatField(help_text="Depth in meters", default=10)
    diameter = models.FloatField(blank=True, null=True, help_text="Diameter (for cylindrical)")
    length = models.FloatField(blank=True, null=True, help_text="Length (for cuboid)")
    width = models.FloatField(blank=True, null=True, help_text="Width (for cuboid)")

    def __str__(self):
        return self.name

    def clean(self):
        if self.design == 'cylindrical':
            if self.flow_type != 'horizontal':
                raise ValidationError('Cylindrical must use horizontal flow.')
            if self.length or self.width:
                raise ValidationError('Length and width must be empty for cylindrical.')
            if not self.diameter:
                raise ValidationError('Diameter is required for cylindrical.')
        elif self.design == 'cuboid':
            if self.flow_type != 'vertical':
                raise ValidationError('Cuboid must use vertical flow.')
            if self.diameter:
                raise ValidationError('Diameter must be empty for cuboid.')
            if not (self.length and self.width):
                raise ValidationError('Length and width are required for cuboid.')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class DisludgeValve(models.Model):
    clarifier = models.ForeignKey(Clarifier, on_delete=models.CASCADE, related_name='disludge_valves')
    name = models.CharField(max_length=100)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.name} - {self.status}"


# ========================
# Abstract Water Quality Limit Base
# ========================
class AbstractWaterLimit(models.Model):
    treatment_plant = models.ForeignKey(TreatmentPlant, on_delete=models.CASCADE)
    min_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        abstract = True


class TreatedWaterLimit(AbstractWaterLimit):
    parameter = models.ForeignKey(PhysicochemicalParameter, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.parameter.name} limit for {self.treatment_plant.name}"


class MicrobialLimit(AbstractWaterLimit):
    parameter = models.ForeignKey(MicrobialParameter, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.parameter.name} limit for {self.treatment_plant.name}"


class HeavyMetalLimit(AbstractWaterLimit):
    parameter = models.ForeignKey(HeavyMetalParameter, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.parameter.name} limit for {self.treatment_plant.name}"


class RawWaterLimit(AbstractWaterLimit):
    parameter = models.ForeignKey(PhysicochemicalParameter, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.parameter.name} limit for {self.treatment_plant.name}"


class ClarifiedWaterLimit(AbstractWaterLimit):
    parameter = models.ForeignKey(PhysicochemicalParameter, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.parameter.name} limit for {self.treatment_plant.name}"


class CoagulatedWaterLimit(AbstractWaterLimit):
    parameter = models.ForeignKey(PhysicochemicalParameter, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.parameter.name} limit for {self.treatment_plant.name}"


class FilteredWaterLimit(AbstractWaterLimit):
    parameter = models.ForeignKey(PhysicochemicalParameter, on_delete=models.CASCADE)
    water_filter = models.ForeignKey(
        WaterFilter,
        on_delete=models.CASCADE,
        related_name='filtered_water_limits',
        null=True,
        blank=True,
        help_text="Filter this parameter limit applies to.",
    )

    def clean(self):
        super().clean()
        if not self.water_filter_id:
            return
        water_filter = self.water_filter
        if water_filter.treatment_plant_id not in (None, self.treatment_plant_id):
            raise ValidationError("The selected filter belongs to a different treatment plant.")
        if not water_filter.phase_id:
            raise ValidationError("A filtered-water limit must be linked to a filter assigned to a phase.")
        if water_filter.phase.treatment_plant_id != self.treatment_plant_id:
            raise ValidationError("The selected filter phase belongs to a different treatment plant.")

    def __str__(self):
        return f"{self.parameter.name} limit for {self.treatment_plant.name}"
