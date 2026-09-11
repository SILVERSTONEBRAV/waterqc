#itinerary/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.functional import cached_property
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from CompanyInfo.models import RegionalInfo
from django.db.models import JSONField
import uuid

# --- Registry Utility ---
class Registry:
    def __init__(self):
        self._registry = {}

    def register(self, key, value):
        self._registry[key] = value

    def get(self, key):
        return self._registry.get(key)

    def all(self):
        return self._registry.values()

# Global Registries
ITINERARY_TYPE_REGISTRY = Registry()
SAMPLING_POINT_TYPE_REGISTRY = Registry()
ASSIGNMENT_STRATEGY_REGISTRY = Registry()

# --- Abstract Audit Model ---
class AuditModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    change_log = JSONField(default=list, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        self.is_deleted = True
        self.save()

    def restore(self):
        self.is_deleted = False
        self.save()

    def log_change(self, message):
        self.change_log.append({
            'timestamp': timezone.now().isoformat(),
            'message': message
        })
        self.save(update_fields=['change_log'])

    @property
    def is_active(self):
        return not self.is_deleted

# --- System Configuration ---
class SystemConfig(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = JSONField(default=dict)

    def __str__(self):
        return self.key

    @staticmethod
    def get_config(key, default=None):
        config = SystemConfig.objects.filter(key=key).first()
        return config.value if config else default

# --- Sampling Plan ---
class SamplingPlan(AuditModel):
    month = models.DateField(help_text="First day of the month")
    target_sampling_points = models.PositiveIntegerField()
    actual_sampled_points = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('month',)
        ordering = ['-month']

    def __str__(self):
        return f"Sampling Plan ({self.month:%B %Y})"

    @cached_property
    def coverage_percentage(self):
        if self.target_sampling_points == 0:
            return 0
        return min(100, round((self.actual_sampled_points / self.target_sampling_points) * 100, 2))

    def refresh_actual_sampled_points(self):
        count = DynamicSamplingPoint.objects.filter(
            point__last_sampled_date__year=self.month.year,
            point__last_sampled_date__month=self.month.month
        ).count()
        self.actual_sampled_points = count
        self.save()

# --- Abstract Sampling Point ---
class SamplingPoint(AuditModel):
    name = models.CharField(max_length=255)
    location = JSONField(default=dict, blank=True, help_text="GPS, elevation, etc.")
    attributes = JSONField(default=dict, blank=True, help_text="Dynamic metadata with schema enforcement")
    last_sampled_date = models.DateField(blank=True, null=True)
    total_times_sampled = models.PositiveIntegerField(default=0)
    preferred_frequency = models.CharField(max_length=50, choices=[('Daily', 'Daily'), ('Weekly', 'Weekly'), ('Monthly', 'Monthly')], default='Monthly')

    class Meta:
        abstract = True

    def __str__(self):
        return self.name

    def validate_metadata(self):
        required_fields = SystemConfig.get_config('sampling_point_metadata_required_fields', [])
        for field in required_fields:
            if field not in self.attributes:
                raise ValidationError(f"Missing required metadata field: {field}")

    def mark_sampled(self, date=None):
        self.last_sampled_date = date or timezone.now().date()
        self.total_times_sampled += 1
        self.save()

    @property
    def is_sampled_this_month(self):
        if not self.last_sampled_date:
            return False
        now = timezone.now().date()
        return self.last_sampled_date.year == now.year and self.last_sampled_date.month == now.month

# --- Specialized Sampling Points ---
class RegionSamplingPoint(SamplingPoint):
    region = models.ForeignKey(RegionalInfo, on_delete=models.CASCADE, related_name='region_sampling_points')

SAMPLING_POINT_TYPE_REGISTRY.register('Region', RegionSamplingPoint)

class FCARegionSamplingPoint(SamplingPoint):
    fca_region_name = models.CharField(max_length=255)

SAMPLING_POINT_TYPE_REGISTRY.register('FCA', FCARegionSamplingPoint)

class Catchment(AuditModel):
    name = models.CharField(max_length=255)
    treatment_plant_name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class CatchmentSamplingPoint(SamplingPoint):
    catchment = models.ForeignKey(Catchment, on_delete=models.CASCADE, related_name='catchment_sampling_points')

SAMPLING_POINT_TYPE_REGISTRY.register('Catchment', CatchmentSamplingPoint)

# --- Dynamic Sampling Point Wrapper ---
class DynamicSamplingPoint(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='dynamic_sampling_points')
    object_id = models.UUIDField()
    point = GenericForeignKey('content_type', 'object_id')

    def __str__(self):
        return str(self.point)

    @property
    def last_sampled_date(self):
        return self.point.last_sampled_date

    @property
    def is_sampled_this_month(self):
        return self.point.is_sampled_this_month

    @property
    def is_active(self):
        return not self.point.is_deleted

    def mark_sampled(self, date=None):
        self.point.mark_sampled(date)

# --- Itinerary ---
class Itinerary(AuditModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Scheduled', 'Scheduled'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Archived', 'Archived'),
    ]

    name = models.CharField(max_length=255)
    sampling_date = models.DateField()
    max_sampling_points = models.PositiveIntegerField(default=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    is_locked = models.BooleanField(default=False)
    assignment_strategy = models.CharField(max_length=100, blank=True, null=True, help_text="Assignment strategy key from registry")
    remarks = models.TextField(blank=True, null=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='itinerary_content_types')
    object_id = models.UUIDField()
    itinerary_type = GenericForeignKey('content_type', 'object_id')

    sampling_points = models.ManyToManyField(DynamicSamplingPoint, related_name='itineraries', blank=True)

    class Meta:
        ordering = ['-sampling_date']

    def __str__(self):
        return f"Itinerary {self.name} ({self.sampling_date})"

    def clean(self):
        if self.sampling_points.count() > self.max_sampling_points:
            raise ValidationError(f"Cannot assign more than {self.max_sampling_points} sampling points.")
        if self.is_locked:
            raise ValidationError("This itinerary is locked and cannot be modified.")

    @property
    def remaining_slots(self):
        return self.max_sampling_points - self.sampling_points.count()

    @property
    def is_full(self):
        return self.sampling_points.count() >= self.max_sampling_points

    def assign_sampling_points(self):
        if not self.assignment_strategy:
            raise ValidationError("No assignment strategy defined.")
        strategy = ASSIGNMENT_STRATEGY_REGISTRY.get(self.assignment_strategy)
        if not strategy:
            raise ValidationError(f"Assignment strategy '{self.assignment_strategy}' not found.")
        strategy.assign(self)

    def lock(self):
        self.is_locked = True
        self.status = 'Scheduled'
        self.save()

    def mark_completed(self):
        self.status = 'Completed'
        self.is_locked = True
        self.save()

# --- Sample Category ---
class SampleCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
