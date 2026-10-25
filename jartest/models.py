#jartest/models.py
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from decimal import Decimal

from accounts.models import CustomUser
from t.models import TreatmentPlant, CoagulatedWaterLimit
from ca.models import Chemical
from o.models import ChemicalCategory
from parameters.models import PhysicochemicalParameter


# ============================
# Shared Review Workflow Mixin
# ============================
class ReviewMixin(models.Model):
    verified_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="%(class)s_verified")
    verified_at = models.DateTimeField(null=True, blank=True)

    confirmed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="%(class)s_confirmed")
    confirmed_at = models.DateTimeField(null=True, blank=True)

    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="%(class)s_approved")
    approved_at = models.DateTimeField(null=True, blank=True)

    needs_review = models.BooleanField(default=False,
                                       help_text="Indicates if this test requires review after reversion.")

    class Meta:
        abstract = True

    def verify(self, user):
        self.verified_by = user
        self.verified_at = timezone.now()
        self.needs_review = False

    def confirm(self, user):
        if not self.verified_at:
            raise ValidationError("Cannot confirm before verification.")
        self.confirmed_by = user
        self.confirmed_at = timezone.now()
        self.needs_review = False

    def approve(self, user):
        if not self.confirmed_at:
            raise ValidationError("Cannot approve before confirmation.")
        self.approved_by = user
        self.approved_at = timezone.now()
        self.needs_review = False

    def revert_verification(self):
        if self.confirmed_at or self.approved_at:
            raise ValidationError("Cannot revert verification after confirmation or approval.")
        self.verified_by = None
        self.verified_at = None
        self.needs_review = True

    def revert_confirmation(self):
        if self.approved_at:
            raise ValidationError("Cannot revert confirmation after approval.")
        self.confirmed_by = None
        self.confirmed_at = None
        self.needs_review = True

    def revert_approval(self):
        self.approved_by = None
        self.approved_at = None
        self.needs_review = True


# ============================
# Raw Water
# ============================
class RawWater(models.Model):
    treatment_plant = models.ForeignKey(TreatmentPlant, on_delete=models.CASCADE, related_name='raw_water_records')
    sampled_at = models.DateTimeField(default=timezone.now)

    source_name = models.CharField(max_length=255)
    location_description = models.TextField(blank=True, null=True)

    coagulant = models.ForeignKey(
        Chemical,
        on_delete=models.PROTECT,
        limit_choices_to={'categories__category': ChemicalCategory.Category.COAGULANT},
        help_text="Selected coagulant used at time of sampling"
    )
    coagulant_concentration_ppm = models.DecimalField(
        max_digits=6, decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Dosage applied (ppm)"
    )

    remarks = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Raw Water Record"
        verbose_name_plural = "Raw Water Records"
        ordering = ['-sampled_at']

    def __str__(self):
        return f"Raw Water @ {self.treatment_plant.name} on {self.sampled_at:%Y-%m-%d %H:%M}"

    def get_expected_parameters(self):
        return CoagulatedWaterLimit.objects.filter(
            treatment_plant=self.treatment_plant
        ).values_list('parameter', flat=True)

    def get_measurement_dict(self):
        return {
            m.parameter.parameter.name.lower(): m.value
            for m in self.analyses.all()
        }


class RawWaterAnalysis(models.Model):
    raw_water = models.ForeignKey(RawWater, on_delete=models.CASCADE, related_name='analyses')
    parameter = models.ForeignKey(CoagulatedWaterLimit, on_delete=models.PROTECT)
    value = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ['raw_water', 'parameter']
        verbose_name = "Raw Water Analysis"
        verbose_name_plural = "Raw Water Analyses"

    def __str__(self):
        return f"{self.parameter.parameter.name}: {self.value} ({self.raw_water})"


# ============================
# Jar Test
# ============================
class JarTest(ReviewMixin):
    treatment_plant = models.ForeignKey(TreatmentPlant, on_delete=models.PROTECT, related_name='jar_tests')
    raw_water = models.ForeignKey(RawWater, on_delete=models.PROTECT, related_name='jar_tests')
    test_date = models.DateField(default=timezone.now)

    coagulant = models.ForeignKey(
        Chemical,
        on_delete=models.PROTECT,
        limit_choices_to={'categories__category': ChemicalCategory.Category.COAGULANT},
        help_text="Coagulant tested"
    )
    established_dosage_mg_per_l = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text="Final recommended dosage based on results"
    )
    analyst = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='performed_jar_tests')
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['treatment_plant', 'test_date']
        ordering = ['-test_date']
        verbose_name = "Jar Test"
        verbose_name_plural = "Jar Tests"

    def __str__(self):
        return f"Jar Test @ {self.treatment_plant.name} on {self.test_date}"

    def get_expected_parameters(self):
        return CoagulatedWaterLimit.objects.filter(
            treatment_plant=self.treatment_plant
        ).values_list('parameter', flat=True)

    def rank_jar_results(self):
        jars = list(self.jar_results.select_related().prefetch_related('measurements'))
        if len(jars) != 6:
            return

        self.jar_results.update(performance_rank=None, is_optimal=False)

        turbidity = PhysicochemicalParameter.objects.filter(name__iexact='turbidity').first()
        color = PhysicochemicalParameter.objects.filter(name__iexact='color').first()
        relevant_params = {turbidity, color}

        scored = sorted(jars, key=lambda jar: jar.performance_score(relevant_params))

        for index, jar in enumerate(scored, start=1):
            jar.performance_rank = index
            jar.is_optimal = (index == 1)
            jar.save(update_fields=['performance_rank', 'is_optimal'])

        self.established_dosage_mg_per_l = scored[0].dosage_mg_per_l
        if self.pk:
            JarTest.objects.filter(pk=self.pk).update(established_dosage_mg_per_l=self.established_dosage_mg_per_l)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        super().save(*args, **kwargs)
        if update_fields and 'established_dosage_mg_per_l' in update_fields:
            return
        if self.pk and self.jar_results.count() == 6:
            self.rank_jar_results()


# ============================
# Jar Result
# ============================
class JarResult(models.Model):
    JAR_NUMBERS = [(i, f"Jar {i}") for i in range(1, 7)]

    jar_test = models.ForeignKey(JarTest, on_delete=models.CASCADE, related_name='jar_results')
    jar_number = models.PositiveSmallIntegerField(choices=JAR_NUMBERS)
    dosage_mg_per_l = models.DecimalField("Dosage (mg/L)", max_digits=5, decimal_places=2,
                                          validators=[MinValueValidator(0)])

    floc_observation_time = models.DurationField(
        null=True, blank=True,
        help_text="Time taken to observe flocs (e.g. 00:03:20)"
    )

    is_optimal = models.BooleanField(default=False)
    performance_rank = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="1 = best performing jar"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['jar_test', 'jar_number']
        ordering = ['performance_rank', 'jar_number']
        verbose_name = "Jar Result"
        verbose_name_plural = "Jar Results"

    def __str__(self):
        return f"{self.jar_test} - Jar {self.jar_number}"

    @property
    def floc_observation_seconds(self):
        return self.floc_observation_time.total_seconds() if self.floc_observation_time else None

    def performance_score(self, relevant_params=None):
        if relevant_params is None:
            turbidity = PhysicochemicalParameter.objects.filter(name__iexact='turbidity').first()
            color = PhysicochemicalParameter.objects.filter(name__iexact='color').first()
            relevant_params = {turbidity, color}

        score = Decimal('0')
        for m in self.measurements.select_related('parameter__parameter').all():
            param_obj = getattr(m.parameter, 'parameter', m.parameter)
            if param_obj in relevant_params or m.parameter in relevant_params:
                score += Decimal(m.value)
        return score


# ============================
# Jar Measurement
# ============================
class JarMeasurement(models.Model):
    jar_result = models.ForeignKey(JarResult, on_delete=models.CASCADE, related_name='measurements')
    parameter = models.ForeignKey(CoagulatedWaterLimit, on_delete=models.PROTECT)
    value = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ['jar_result', 'parameter']
        verbose_name = "Jar Measurement"
        verbose_name_plural = "Jar Measurements"

    def __str__(self):
        return f"{self.parameter.parameter.name}: {self.value} ({self.jar_result})"


# ============================
# Utility Function
# ============================
def get_latest_dosage(chemical, treatment_plant):
    """
    Fetch the latest APPROVED dosage for a given coagulant and treatment plant.
    """
    latest_test = (
        JarTest.objects.filter(
            coagulant=chemical,
            treatment_plant=treatment_plant,
            established_dosage_mg_per_l__isnull=False,
            approved_at__isnull=False
        )
        .order_by("-test_date", "-id")
        .first()
    )
    return latest_test.established_dosage_mg_per_l if latest_test else None
