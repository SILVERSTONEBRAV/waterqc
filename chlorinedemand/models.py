#chlorinedemand/models.py
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal

from accounts.models import CustomUser
from t.models import TreatmentPlant


# ============================
# Review Workflow Mixin
# ============================
class ReviewMixin(models.Model):
    verified_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="%(class)s_verified")
    verified_at = models.DateTimeField(null=True, blank=True)

    confirmed_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="%(class)s_confirmed")
    confirmed_at = models.DateTimeField(null=True, blank=True)

    approved_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="%(class)s_approved")
    approved_at = models.DateTimeField(null=True, blank=True)

    needs_review = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def verify(self, user):
        self.verified_by = user
        self.verified_at = timezone.now()
        self.needs_review = False

    def confirm(self, user):
        if not self.verified_at:
            raise ValidationError("Verify before confirming.")
        self.confirmed_by = user
        self.confirmed_at = timezone.now()
        self.needs_review = False

    def approve(self, user):
        if not self.confirmed_at:
            raise ValidationError("Confirm before approving.")
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
# Chlorine Demand Test
# ============================
class ChlorineDemandTest(ReviewMixin):
    treatment_plant = models.ForeignKey(TreatmentPlant, on_delete=models.PROTECT, related_name='chlorine_demand_tests')
    test_date = models.DateField(default=timezone.now)
    analyst = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='performed_chlorine_tests')

    established_dosage_mg_per_l = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Final recommended chlorine dosage (mg/L)"
    )

    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Chlorine Demand Test"
        verbose_name_plural = "Chlorine Demand Tests"
        unique_together = ['treatment_plant', 'test_date']
        ordering = ['-test_date']

    def __str__(self):
        return f"Chlorine Test @ {self.treatment_plant.name} - {self.test_date}"

    def rank_results(self):
        jars = list(self.jar_results.all())
        if len(jars) < 1:
            return

        self.jar_results.update(performance_rank=None, is_optimal=False)
        target = Decimal("0.2")
        scored = sorted(jars, key=lambda j: abs((j.residual_chlorine or 0) - target))

        for index, jar in enumerate(scored, start=1):
            jar.performance_rank = index
            jar.is_optimal = (index == 1)
            jar.save(update_fields=['performance_rank', 'is_optimal'])

        self.established_dosage_mg_per_l = scored[0].dosage_mg_per_l
        self.save(update_fields=['established_dosage_mg_per_l'])

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.jar_results.exists():
            self.rank_results()


# ============================
# Chlorine Jar Result
# ============================
class ChlorineJarResult(models.Model):
    JAR_NUMBERS = [(i, f"Jar {i}") for i in range(1, 7)]

    test = models.ForeignKey(ChlorineDemandTest, on_delete=models.CASCADE, related_name='jar_results')
    jar_number = models.PositiveSmallIntegerField(choices=JAR_NUMBERS)
    dosage_mg_per_l = models.DecimalField("Dosage (mg/L)", max_digits=5, decimal_places=2)

    residual_chlorine = models.DecimalField(
        max_digits=5, decimal_places=3,
        null=True, blank=True,
        help_text="Residual chlorine (mg/L) after contact time"
    )

    performance_rank = models.PositiveSmallIntegerField(null=True, blank=True)
    is_optimal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['test', 'jar_number']
        ordering = ['performance_rank', 'jar_number']
        verbose_name = "Chlorine Jar Result"
        verbose_name_plural = "Chlorine Jar Results"

    def __str__(self):
        return f"{self.test} - Jar {self.jar_number}"

    def clean(self):
        if self.dosage_mg_per_l < 0:
            raise ValidationError("Dosage must be non-negative.")
        if self.residual_chlorine is not None and self.residual_chlorine < 0:
            raise ValidationError("Residual chlorine must be non-negative.")
