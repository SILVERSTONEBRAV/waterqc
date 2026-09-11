#parameters/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
import uuid
import string
import random

def generate_uuid():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


# --- Utility ---
class ParameterUnit(models.TextChoices):
    MG_L = 'mg/L', 'mg/L'
    UG_L = 'µg/L', 'µg/L'
    ml = 'ml', 'ml'
    NTU = 'NTU', 'NTU'
    CFU_100ML = 'CFU/100mL', 'CFU'
    PH_UNITS = 'pH units', 'pH'
    TEMP_C = '°C', '°C'
    PERCENT = '%', '%'
    MPN = 'MPN/100mL', 'MPN'
    US_CM = 'µS/cm', 'µS/cm'  # Conductivity
    #MS_CM = 'mS/cm', 'MilliSiemens per centimeter (mS/cm)'  # High Conductivity ranges
    HAZEN_UNITS = 'HU', 'HU'
    PPM = 'ppm', 'ppm'
    PPT = 'ppt', 'Parts per Thousand (ppt)'


# --- Abstract Base Audit Model ---
class AuditModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, help_text="Set false to soft-delete the record")

    class Meta:
        abstract = True

# --- Abstract Base Parameter Model ---
class BaseParameter(AuditModel):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=100, unique=True)
    unit = models.CharField(max_length=30, choices=ParameterUnit.choices, default=ParameterUnit.MG_L)

    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.unit})"

# --- Specialized Parameter Types ---
class PhysicochemicalParameter(BaseParameter):
    """Physical and chemical water quality parameters (e.g., pH, Turbidity)."""
    pass

class MicrobialParameter(BaseParameter):
    """Biological/microbial water quality parameters (e.g., E.coli, Total coliform)."""
    pass

class HeavyMetalParameter(BaseParameter):
    """Heavy metals parameters (e.g., Lead, Mercury, Arsenic)."""
    pass

# --- Parameters with Regulatory Standards ---
class StandardizedParameter(BaseParameter):
    min_standard = models.DecimalField(
        max_digits=8, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.000'))],
        help_text="Minimum acceptable value (regulatory standard)"
    )
    max_standard = models.DecimalField(
        max_digits=8, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.000'))],
        help_text="Maximum acceptable value (regulatory standard)"
    )

    class Meta:
        abstract = True

    def clean(self):
        if self.min_standard >= self.max_standard:
            raise ValidationError("Minimum standard must be less than maximum standard.")

    def is_within_standard(self, value):
        return self.min_standard <= value <= self.max_standard

# --- Concrete Standardized Parameters ---
class WWQParameter_qad(StandardizedParameter):
    class Meta:
        verbose_name = "Wastewater Quality Parameter (NEMA)"
        verbose_name_plural = "Wastewater Quality Parameters (NEMA)"

class CWQParameter_qad(StandardizedParameter):
    class Meta:
        verbose_name = "Portable Water Quality Parameter (KEBS)"
        verbose_name_plural = "Portable Water Quality Parameters (KEBS)"

class DistributionParameter_qad(StandardizedParameter):
    class Meta:
        verbose_name = "Distribution Water Quality Parameter (KEBS)"
        verbose_name_plural = "Distribution Water Quality Parameters (KEBS)"

class GigiriParameter_qad(StandardizedParameter):
    class Meta:
        verbose_name = "Gigiri Clean Water Quality Parameter"
        verbose_name_plural = "Gigiri Clean Water Quality Parameters"

class KabeteParameter_qad(StandardizedParameter):
    class Meta:
        verbose_name = "Kabete Quality Assurance Parameter"
        verbose_name_plural = "Kabete Quality Assurance Parameters"

class MicrobialParameter_qad(StandardizedParameter):
    class Meta:
        verbose_name = "Microbial Water Quality Parameter"
        verbose_name_plural = "Microbial Water Quality Parameters"

# --- Non-standardized Parameter ---
class CatchmentParameter_qad(BaseParameter):
    class Meta:
        verbose_name = "Catchment Water Quality Parameter"
        verbose_name_plural = "Catchment Water Quality Parameters"

# --- Optional ParameterType Registry ---
class ParameterTypeRegistry:
    _registry = {}

    @classmethod
    def register(cls, key, param_class):
        cls._registry[key] = param_class

    @classmethod
    def get(cls, key):
        return cls._registry.get(key)

    @classmethod
    def all_types(cls):
        return cls._registry.keys()

# Registering types
ParameterTypeRegistry.register('WWQ', WWQParameter_qad)
ParameterTypeRegistry.register('CWQ', CWQParameter_qad)
ParameterTypeRegistry.register('Distribution', DistributionParameter_qad)
ParameterTypeRegistry.register('Gigiri', GigiriParameter_qad)
ParameterTypeRegistry.register('Kabete', KabeteParameter_qad)
ParameterTypeRegistry.register('Catchment', CatchmentParameter_qad)
ParameterTypeRegistry.register('Microbial', MicrobialParameter_qad)
