#wc/models.py
import uuid
from datetime import timedelta
from django.db import models, transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import JSONField
from accounts.models import CustomUser
from CompanyInfo.models import RegionalInfo, ZonalInfo, SubZonalInfo
from parameters.models import DistributionParameter_qad
from t.models import MicrobialLimit
from django.utils import timezone

# --- Utility Functions ---
def generate_short_uuid():
    return uuid.uuid4().hex[:8].upper()

# --- Abstract Models ---
class AuditModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def soft_delete(self, user):
        self.is_deleted = True
        self.save()
        ComplaintAuditTrail.objects.create(
            complaint=getattr(self, 'complaint', None),
            action='Soft Deleted',
            performed_by=user,
            details={"model": self.__class__.__name__}
        )

class StateModel(models.Model):
    state = models.CharField(max_length=50)

    class Meta:
        abstract = True

    def transition_state(self, new_state, transitions, permissions, user):
        if new_state not in transitions.get(self.state, []):
            raise ValidationError(f"Invalid transition from {self.state} to {new_state}")
        required_perm = permissions.get(new_state)
        if required_perm and not user.has_perm(required_perm):
            raise PermissionDenied(f"User lacks permission: {required_perm}")
        self.state = new_state
        self.save()
        if hasattr(self, 'complaint'):
            ComplaintAuditTrail.objects.create(
                complaint=self.complaint,
                action=f"State changed to {new_state}",
                performed_by=user,
                details={"model": self.__class__.__name__}
            )

# --- Lookup Tables ---
class WaterQualityComplaintCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class SampleCondition(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

# --- Main Complaint Model ---
class WaterQualityComplaint(AuditModel):
    reference_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='complaints')
    category = models.ForeignKey(WaterQualityComplaintCategory, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=[
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('RESOLVED', 'Resolved'),
        ('CLOSED', 'Closed')
    ], default='PENDING')
    contact_number = models.CharField(max_length=20, null=True, blank=True)

    region = models.ForeignKey(RegionalInfo, on_delete=models.SET_NULL, null=True, blank=True)
    zone = models.ForeignKey(ZonalInfo, on_delete=models.SET_NULL, null=True, blank=True)
    sub_zone = models.ForeignKey(SubZonalInfo, on_delete=models.SET_NULL, null=True, blank=True)

    location_description = models.CharField(max_length=255, null=True, blank=True)
    geo_coordinates = JSONField(null=True, blank=True)

    feedback = models.TextField(blank=True, null=True)

    escalation_level = models.PositiveIntegerField(default=0, help_text="Tracks escalation levels of unresolved complaints")

    def __str__(self):
        return f"{self.reference_id} - {self.title}"

    def escalate(self, user):
        self.escalation_level += 1
        self.save()
        ComplaintAuditTrail.objects.create(
            complaint=self,
            action=f"Escalated to Level {self.escalation_level}",
            performed_by=user,
            details={}
        )

# --- Complaint Post & Resolution History ---
class ComplaintPost(AuditModel):
    complaint = models.ForeignKey(WaterQualityComplaint, on_delete=models.CASCADE, related_name='posts')
    content = models.TextField()
    posted_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    posted_at = models.DateTimeField(auto_now_add=True)

class ComplaintResolution(AuditModel):
    complaint = models.ForeignKey(WaterQualityComplaint, on_delete=models.CASCADE, related_name='resolutions')
    resolution_details = models.TextField()
    resolved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    resolved_at = models.DateTimeField(auto_now_add=True)

# --- Attachments & Status Logs ---
class ComplaintAttachment(AuditModel):
    complaint = models.ForeignKey(WaterQualityComplaint, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='complaint_attachments/')

class ComplaintStatusLog(models.Model):
    complaint = models.ForeignKey(WaterQualityComplaint, on_delete=models.CASCADE, related_name='status_logs')
    previous_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True, null=True)

# --- Water Sample ---
class WaterSample(AuditModel):
    complaint = models.OneToOneField(WaterQualityComplaint, on_delete=models.CASCADE, related_name='sample')
    sample_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    collection_date = models.DateTimeField(default=timezone.now)

    source_type = models.CharField(max_length=50)
    sampling_method = models.CharField(max_length=50)

    conditions = models.ManyToManyField(SampleCondition, related_name='samples', blank=True)
    remarks = models.TextField(blank=True, null=True)

    sampling_coordinates = JSONField(null=True, blank=True)

    def __str__(self):
        return f"Sample {self.sample_id}"

# --- Parameter Analysis ---
class WaterSampleParameterResult(AuditModel):
    sample = models.ForeignKey(WaterSample, on_delete=models.CASCADE, related_name='parameter_results')
    parameter = models.ForeignKey(DistributionParameter_qad, on_delete=models.CASCADE)
    measured_value = models.DecimalField(max_digits=10, decimal_places=3)
    unit = models.CharField(max_length=50, blank=True, null=True)
    is_compliant = models.BooleanField(default=True)
    remarks = models.TextField(blank=True, null=True)

    analyzed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    analyzed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('sample', 'parameter')

# --- Microbial Analysis ---
class ComplaintMicrobialAnalysis(StateModel, AuditModel):
    uuid = models.CharField(max_length=8, unique=True, default=generate_short_uuid, editable=False)
    sample = models.OneToOneField(WaterSample, on_delete=models.CASCADE, related_name='microbial_analysis')
    sampling_date = models.DateField(default=timezone.now)

    created_by = models.ForeignKey(CustomUser, null=True, on_delete=models.SET_NULL,
                                   related_name='complaint_microbial_created')
    analysed_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='complaint_microbial_analysed')
    verified_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='complaint_microbial_verified')
    confirmed_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='complaint_microbial_confirmed')
    approved_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='complaint_microbial_approved')

    incubation_start = models.DateTimeField(default=timezone.now)
    incubation_end = models.DateTimeField(null=True, blank=True)

    remarks = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.incubation_start and not self.incubation_end:
            self.incubation_end = self.incubation_start + timedelta(hours=24)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.uuid} – {self.sample.sample_id}"

    def transition_state(self, new_state, user):
        transitions = {
            'new': ['analysed'],
            'analysed': ['verified'],
            'verified': ['confirmed'],
            'confirmed': ['approved']
        }
        permissions = {
            'analysed': 'complaints.change_complaintmicrobialanalysis',
            'verified': 'complaints.verify_complaintmicrobialanalysis',
            'confirmed': 'complaints.confirm_complaintmicrobialanalysis',
            'approved': 'complaints.approve_complaintmicrobialanalysis',
        }
        super().transition_state(new_state, transitions, permissions, user)

class ComplaintMicrobialParameterResult(AuditModel):
    analysis = models.ForeignKey(ComplaintMicrobialAnalysis, on_delete=models.CASCADE, related_name='parameter_results')
    parameter = models.ForeignKey(MicrobialLimit, on_delete=models.CASCADE)
    result_value = models.DecimalField(max_digits=10, decimal_places=2)
    remarks = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ('analysis', 'parameter')

    def __str__(self):
        return f"{self.analysis.uuid} - {self.parameter.parameter.name}: {self.result_value}"

# --- Confirmation Report ---
class ComplaintConfirmationReport(AuditModel):
    complaint = models.OneToOneField(WaterQualityComplaint, on_delete=models.CASCADE, related_name='confirmation_report')
    confirmation_sample = models.OneToOneField(WaterSample, on_delete=models.CASCADE, related_name='confirmation_sample', null=True, blank=True)
    confirmation_summary = models.TextField()
    confirmed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    confirmed_at = models.DateTimeField(default=timezone.now)
    is_confirmed = models.BooleanField(default=False)

    def __str__(self):
        return f"Confirmation Report for {self.complaint.reference_id}"

# --- Advanced Audit Trail ---
class ComplaintAuditTrail(models.Model):
    complaint = models.ForeignKey(WaterQualityComplaint, on_delete=models.CASCADE, related_name='audit_trails')
    action = models.CharField(max_length=100)
    performed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.action} on {self.timestamp} by {self.performed_by}"
