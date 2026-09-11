#central_lab/models.py
from django.db import models
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.exceptions import ValidationError
import string
import random
import uuid

from accounts.models import CustomUser
from parameters.models import (
    DistributionParameter_qad,
    KabeteParameter_qad,
    GigiriParameter_qad,
    CatchmentParameter_qad
)
from analysis_methods.models import WWAnalysisMethod
from CompanyInfo.models import RegionalInfo
from itinerary.models import (
    RegionSamplingPoint,
    FCARegionSamplingPoint,
    CatchmentSamplingPoint,
    DynamicSamplingPoint,
    Itinerary
)


# --- Utility ---
def generate_reference_id(length=12):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# --- Audit Base ---
class AuditModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def soft_delete(self):
        self.is_deleted = True
        self.save()

    def restore(self):
        self.is_deleted = False
        self.save()

    @property
    def is_active(self):
        return not self.is_deleted


class KabeteSamplingPoint(AuditModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    gps_coordinates = models.JSONField(blank=True, null=True)

    def __str__(self):
        return self.name


class GigiriSamplingPoint(AuditModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    gps_coordinates = models.JSONField(blank=True, null=True)

    def __str__(self):
        return self.name


# --- SampleCategory ---
class SampleCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

# --- Generic Sample ---
class GenericSample(AuditModel):
    reference_id = models.CharField(max_length=12, default=generate_reference_id, unique=True, db_index=True)
    sampling_date = models.DateField()
    sampling_time = models.TimeField()
    remarks = models.TextField(blank=True, null=True)
    barcode = models.CharField(max_length=255, unique=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.barcode:
            self.barcode = f"{self.reference_id}-{self.sampling_date.strftime('%Y%m%d')}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Sample {self.reference_id}"

# --- Sample Models ---
class RegionSample(GenericSample):
    sampling_point = models.ForeignKey(RegionSamplingPoint, on_delete=models.PROTECT, related_name='samples')
    category = models.ForeignKey(SampleCategory, on_delete=models.PROTECT, related_name='region_samples')

class FCASample(GenericSample):
    sampling_point = models.ForeignKey(FCARegionSamplingPoint, on_delete=models.PROTECT, related_name='samples')

class CatchmentSample(GenericSample):
    sampling_point = models.ForeignKey(CatchmentSamplingPoint, on_delete=models.PROTECT, related_name='samples')

class KabeteSample(GenericSample):
    sampling_point = models.ForeignKey(KabeteSamplingPoint, on_delete=models.PROTECT, related_name='samples')

class GigiriSample(GenericSample):
    sampling_point = models.ForeignKey(GigiriSamplingPoint, on_delete=models.PROTECT, related_name='samples')

# --- Analysis Workflow ---
class WaterAnalysisState(models.TextChoices):
    NEW = "NEW", "New"
    ANALYSED = "ANALYSED", "Analysed"
    VERIFIED = "VERIFIED", "Verified"
    CONFIRMED = "CONFIRMED", "Confirmed"
    APPROVED = "APPROVED", "Approved"

STATE_TRANSITIONS = {
    WaterAnalysisState.NEW: [WaterAnalysisState.ANALYSED],
    WaterAnalysisState.ANALYSED: [WaterAnalysisState.VERIFIED],
    WaterAnalysisState.VERIFIED: [WaterAnalysisState.CONFIRMED],
    WaterAnalysisState.CONFIRMED: [WaterAnalysisState.APPROVED],
    WaterAnalysisState.APPROVED: [],
}

STATE_USER_FIELD = {
    WaterAnalysisState.ANALYSED: "analysed_by",
    WaterAnalysisState.VERIFIED: "verified_by",
    WaterAnalysisState.CONFIRMED: "confirmed_by",
    WaterAnalysisState.APPROVED: "approved_by",
}

class GenericAnalysis(AuditModel):
    status = models.CharField(max_length=20, choices=WaterAnalysisState.choices, default=WaterAnalysisState.NEW)
    analysed_by = models.ForeignKey(CustomUser, on_delete=models.PROTECT, null=True, blank=True, related_name="%(class)s_analysed")
    verified_by = models.ForeignKey(CustomUser, on_delete=models.PROTECT, null=True, blank=True, related_name="%(class)s_verified")
    confirmed_by = models.ForeignKey(CustomUser, on_delete=models.PROTECT, null=True, blank=True, related_name="%(class)s_confirmed")
    approved_by = models.ForeignKey(CustomUser, on_delete=models.PROTECT, null=True, blank=True, related_name="%(class)s_approved")
    analysis_datetime = models.DateTimeField(default=timezone.now)
    remarks = models.TextField(blank=True)

    class Meta:
        abstract = True

    def clean(self):
        if isinstance(self.analysis_datetime, str):
            parsed = parse_datetime(self.analysis_datetime)
            if parsed:
                self.analysis_datetime = parsed
            else:
                raise ValidationError("Invalid datetime format for analysis_datetime.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def change_status(self, new_state, user):
        if new_state not in STATE_TRANSITIONS[self.status]:
            raise ValidationError(f"Cannot transition from {self.status} to {new_state}")
        field = STATE_USER_FIELD.get(new_state)
        if field:
            setattr(self, field, user)
        self.status = new_state
        self.save()

# --- Analysis Models ---
class RegionSampleAnalysis(GenericAnalysis):
    sample = models.OneToOneField(RegionSample, on_delete=models.CASCADE, related_name='analysis')

class FCASampleAnalysis(GenericAnalysis):
    sample = models.OneToOneField(FCASample, on_delete=models.CASCADE, related_name='analysis')

class CatchmentSampleAnalysis(GenericAnalysis):
    sample = models.OneToOneField(CatchmentSample, on_delete=models.CASCADE, related_name='analysis')

class KabeteSampleAnalysis(GenericAnalysis):
    sample = models.OneToOneField(KabeteSample, on_delete=models.CASCADE, related_name='analysis')

class GigiriSampleAnalysis(GenericAnalysis):
    sample = models.OneToOneField(GigiriSample, on_delete=models.CASCADE, related_name='analysis')

# --- Parameter Results ---
class GenericParameterResult(AuditModel):
    analysis_method = models.ForeignKey(WWAnalysisMethod, on_delete=models.CASCADE)
    result = models.DecimalField(max_digits=10, decimal_places=2)
    kebs_reference = models.CharField(max_length=255, editable=False)
    quality_compliance = models.CharField(max_length=20, editable=False)

    class Meta:
        abstract = True
        unique_together = ('analysis', 'parameter')

    def save(self, *args, **kwargs):
        self.kebs_reference = self.analysis_method.reference
        try:
            if self.parameter.min_standard <= self.result <= self.parameter.max_standard:
                self.quality_compliance = "Complying"
            else:
                self.quality_compliance = "Not Complying"
        except (AttributeError, TypeError):
            self.quality_compliance = "N/A"
        super().save(*args, **kwargs)

class RegionSampleParameterResult(GenericParameterResult):
    analysis = models.ForeignKey(RegionSampleAnalysis, on_delete=models.CASCADE, related_name='parameter_results')
    parameter = models.ForeignKey(DistributionParameter_qad, on_delete=models.CASCADE)

class FCASampleParameterResult(GenericParameterResult):
    analysis = models.ForeignKey(FCASampleAnalysis, on_delete=models.CASCADE, related_name='parameter_results')
    parameter = models.ForeignKey(DistributionParameter_qad, on_delete=models.CASCADE)

class CatchmentSampleParameterResult(GenericParameterResult):
    analysis = models.ForeignKey(CatchmentSampleAnalysis, on_delete=models.CASCADE, related_name='parameter_results')
    parameter = models.ForeignKey(CatchmentParameter_qad, on_delete=models.CASCADE)

class KabeteSampleParameterResult(GenericParameterResult):
    analysis = models.ForeignKey(KabeteSampleAnalysis, on_delete=models.CASCADE, related_name='parameter_results')
    parameter = models.ForeignKey(KabeteParameter_qad, on_delete=models.CASCADE)

class GigiriSampleParameterResult(GenericParameterResult):
    analysis = models.ForeignKey(GigiriSampleAnalysis, on_delete=models.CASCADE, related_name='parameter_results')
    parameter = models.ForeignKey(GigiriParameter_qad, on_delete=models.CASCADE)
