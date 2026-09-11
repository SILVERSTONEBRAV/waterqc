#filtered_water/models.py
import uuid
from enum import Enum
from datetime import datetime
from django.db import models
from django.utils.timezone import now
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.validators import MinValueValidator
from accounts.models import CustomUser
from t.models import TreatmentPlantPhase, TreatmentPlant, FilteredWaterLimit, WaterFilter
from sc.models import ShiftAssignment  # Make sure this is correct

User = CustomUser


# ============================
# ✅ ENUM DEFINITIONS
# ============================

class FilteredWaterAnalysisState(str, Enum):
    NEW = 'new'
    ANALYSED = 'analysed'
    VERIFIED = 'verified'

    @classmethod
    def choices(cls):
        return [(key.value, key.name.capitalize()) for key in cls]


class WaterFilterStatus(str, Enum):
    WORKING = 'working'
    BACKWASHING = 'backwashing'
    ISOLATED = 'isolated'

    @classmethod
    def choices(cls):
        return [(key.value, key.name.capitalize()) for key in cls]


# ============================
# ✅ TRANSITIONS & PERMISSIONS
# ============================

STATE_TRANSITIONS = {
    FilteredWaterAnalysisState.NEW: [FilteredWaterAnalysisState.ANALYSED],
    FilteredWaterAnalysisState.ANALYSED: [FilteredWaterAnalysisState.VERIFIED],
}

STATE_PERMISSIONS = {
    FilteredWaterAnalysisState.ANALYSED: 't.change_filteredwateranalysis',
    FilteredWaterAnalysisState.VERIFIED: 't.verify_filteredwateranalysis',
}


# ============================
# ✅ ABSTRACT BASE
# ============================

class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ============================
# ✅ MAIN MODELS
# ============================

class FilteredWaterAnalysis(TimestampedModel):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    treatment_plant = models.ForeignKey(TreatmentPlant, on_delete=models.CASCADE, related_name='filtered_analyses', db_index=True)
    treatment_plant_phase = models.ForeignKey(TreatmentPlantPhase, on_delete=models.CASCADE, related_name='filtered_analyses', db_index=True)

    analysed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='filtered_analysed')
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='filtered_verified')

    state = models.CharField(max_length=20, choices=FilteredWaterAnalysisState.choices(), default=FilteredWaterAnalysisState.NEW.value)
    remarks = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = 'Filtered Water Analysis'
        verbose_name_plural = 'Filtered Water Analyses'
        unique_together = ('treatment_plant', 'treatment_plant_phase', 'timestamp')
        ordering = ['-created_at']
        permissions = [
            ('verify_filteredwateranalysis', 'Can verify filtered water analysis'),
        ]

    def __str__(self):
        return f"Filtered {str(self.uuid)[:8]} – {self.treatment_plant.name} ({self.timestamp:%Y-%m-%d %H:%M})"

    def clean(self):
        if self.treatment_plant_phase.treatment_plant != self.treatment_plant:
            raise ValidationError("The selected treatment plant phase does not belong to the specified treatment plant.")

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        # 🔁 Auto-generate results only on creation
        if is_new:
            filters = WaterFilter.objects.filter(
                treatment_plant_phase=self.treatment_plant_phase,
                status=WaterFilterStatus.WORKING.value
            )
            limits = FilteredWaterLimit.objects.filter(
                treatment_plant=self.treatment_plant,
                water_filter__in=filters
            )
            results = [
                FilteredWaterResults(
                    analysis=self,
                    water_filter=limit.water_filter,
                    parameter=limit,
                    result_value=0  # or leave null if preferable
                )
                for limit in limits
            ]
            FilteredWaterResults.objects.bulk_create(results)

    def get_parameters(self):
        filters = WaterFilter.objects.filter(treatment_plant_phase=self.treatment_plant_phase)
        parameters = FilteredWaterLimit.objects.filter(
            treatment_plant=self.treatment_plant,
            water_filter__in=filters
        ).values_list('parameter__name', flat=True).distinct()
        return list(parameters)

    def transition_state(self, new_state: str, user: User):
        current_state = FilteredWaterAnalysisState(self.state)

        if new_state not in [s.value for s in STATE_TRANSITIONS.get(current_state, [])]:
            raise ValidationError(f"Invalid transition from {self.state} to {new_state}.")

        required_perm = STATE_PERMISSIONS.get(FilteredWaterAnalysisState(new_state))
        if required_perm and not user.has_perm(required_perm):
            raise PermissionDenied(f"You lack permission: {required_perm}")

        # ✅ Shift + Time Window Check
        now_dt = now()
        now_date = now_dt.date()
        now_time = now_dt.time()

        shift_qs = ShiftAssignment.objects.select_related('shift').filter(
            employee=user,
            date=now_date,
            attendance_status='present',
            shift__treatment_plant=self.treatment_plant
        )

        valid_shifts = [
            sa for sa in shift_qs
            if sa.shift.start_time <= now_time <= sa.shift.end_time
        ]

        if not valid_shifts:
            raise PermissionDenied("You are not currently within your assigned shift for this treatment plant.")

        # 👤 Attribution
        if new_state == FilteredWaterAnalysisState.ANALYSED.value:
            self.analysed_by = user
        elif new_state == FilteredWaterAnalysisState.VERIFIED.value:
            self.verified_by = user

        # ➕ Transition Log
        FilteredWaterAnalysisTransition.objects.create(
            analysis=self,
            from_state=self.state,
            to_state=new_state,
            performed_by=user
        )

        self.state = new_state
        self.save()


class FilteredWaterAnalysisTransition(TimestampedModel):
    analysis = models.ForeignKey(FilteredWaterAnalysis, on_delete=models.CASCADE, related_name='transitions')
    from_state = models.CharField(max_length=20)
    to_state = models.CharField(max_length=20)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    transition_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Filtered Water Analysis Transition'
        verbose_name_plural = 'Filtered Water Analysis Transitions'
        ordering = ['-transition_time']

    def __str__(self):
        return f"{self.analysis} | {self.from_state} → {self.to_state} by {self.performed_by}"


class FilteredWaterResults(TimestampedModel):
    analysis = models.ForeignKey(FilteredWaterAnalysis, on_delete=models.CASCADE, related_name='results', db_index=True)
    water_filter = models.ForeignKey(WaterFilter, on_delete=models.CASCADE, related_name='results')
    parameter = models.ForeignKey(FilteredWaterLimit, on_delete=models.CASCADE, related_name='results')

    result_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Measured value for this parameter on the specific filter."
    )

    class Meta:
        verbose_name = "Filtered Water Result"
        verbose_name_plural = "Filtered Water Results"
        unique_together = ('analysis', 'water_filter', 'parameter')
        ordering = ['analysis', 'water_filter', 'parameter']
        indexes = [
            models.Index(fields=['analysis', 'water_filter']),
        ]

    def __str__(self):
        return f"{self.parameter.parameter.name} on {self.water_filter.name}: {self.result_value}"

    def clean(self):
        if self.parameter.treatment_plant != self.analysis.treatment_plant:
            raise ValidationError("Selected parameter does not match the analysis treatment plant.")
        if self.parameter.water_filter != self.water_filter:
            raise ValidationError("Selected parameter does not belong to the specified water filter.")
        if self.water_filter.status != WaterFilterStatus.WORKING.value:
            raise ValidationError(
                f"Cannot save result: water filter '{self.water_filter.name}' is currently '{self.water_filter.status}'. "
                "Only filters in 'working' status can have results recorded."
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def parameter_name(self):
        return self.parameter.parameter.name
