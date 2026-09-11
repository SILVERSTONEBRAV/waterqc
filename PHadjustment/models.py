#PHadjustment/models.py
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.contrib.auth import get_user_model

User = get_user_model()  # <-- safe reference to your custom user model

from ca.models import Chemical
from o.models import ChemicalCategory
from jartest.models import JarTest, JarResult

# ============================
# Shared Review Workflow
# ============================
class ReviewMixin(models.Model):
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="%(class)s_verified"
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    confirmed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="%(class)s_confirmed"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)

    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="%(class)s_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    needs_review = models.BooleanField(
        default=False,
        help_text="Indicates if this test requires review after reversion."
    )

    class Meta:
        abstract = True

    def verify(self, user: User):
        self.verified_by = user
        self.verified_at = timezone.now()
        self.needs_review = False

    def confirm(self, user: User):
        if not self.verified_at:
            raise ValidationError("Cannot confirm before verification.")
        self.confirmed_by = user
        self.confirmed_at = timezone.now()
        self.needs_review = False

    def approve(self, user: User):
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
# PH Adjustment Test
# ============================
class PHAdjustmentTest(ReviewMixin):
    treatment_plant = models.ForeignKey(
        JarTest._meta.get_field('treatment_plant').remote_field.model,
        on_delete=models.PROTECT,
        related_name='ph_adjustment_tests'
    )
    source_jar = models.ForeignKey(
        JarResult,
        on_delete=models.PROTECT,
        related_name='ph_adjustment_tests',
        help_text="Jar from JarTest that yielded established dosage"
    )
    test_date = models.DateField(default=timezone.now)
    analyst = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ph_adjustment_tests'
    )
    established_dosage_ml = models.DecimalField(
        "Optimal Dosage (mL)",
        max_digits=6, decimal_places=2,
        null=True, blank=True
    )
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pH Adjustment Test"
        verbose_name_plural = "pH Adjustment Tests"
        ordering = ['-test_date']

    def __str__(self):
        return f"{self.treatment_plant.name} | {self.test_date}"

    def initialize_jars(self, dosages=None):
        """Automatically create six jars for this test using source jar dosage."""
        if self.results.exists():
            return  # already initialized

        base_dosage = self.source_jar.dosage_mg_per_l
        if dosages is None:
            step = base_dosage * Decimal('0.05')
            dosages = [
                base_dosage - 2*step, base_dosage - step, base_dosage,
                base_dosage + step, base_dosage + 2*step, base_dosage + 3*step
            ]

        for idx, dose in enumerate(dosages, start=1):
            PHAdjustmentJarResult.objects.create(
                test=self,
                jar_number=idx,
                dosage_ml=dose
            )

    def rank_results(self):
        jars = list(self.results.all())
        if len(jars) != 6:
            return

        self.results.update(performance_rank=None, is_optimal=False)
        target_ph = Decimal('7.00')
        scored = sorted(jars, key=lambda j: abs((j.resulting_ph or Decimal('0')) - target_ph))

        for idx, jar in enumerate(scored, start=1):
            jar.performance_rank = idx
            jar.is_optimal = (idx == 1)
            jar.save(update_fields=['performance_rank', 'is_optimal'])

        self.established_dosage_ml = scored[0].dosage_ml
        self.save(update_fields=['established_dosage_ml'])


# ============================
# PH Adjustment Jar Result
# ============================
class PHAdjustmentJarResult(models.Model):
    test = models.ForeignKey(
        PHAdjustmentTest,
        on_delete=models.CASCADE,
        related_name='results'
    )
    jar_number = models.PositiveSmallIntegerField()
    dosage_ml = models.DecimalField("Dosage (mL)", max_digits=6, decimal_places=2)
    resulting_ph = models.DecimalField("Resulting pH", max_digits=4, decimal_places=2, null=True, blank=True)
    performance_rank = models.PositiveSmallIntegerField(null=True, blank=True)
    is_optimal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['test', 'jar_number']
        ordering = ['performance_rank', 'jar_number']
        verbose_name = "pH Adjustment Jar Result"
        verbose_name_plural = "pH Adjustment Jar Results"

    def __str__(self):
        return f"{self.test} - Jar {self.jar_number}"

    def clean(self):
        if self.dosage_ml < 0:
            raise ValidationError("Dosage must be non-negative.")
        if self.resulting_ph is not None and not (0 <= self.resulting_ph <= 14):
            raise ValidationError("Resulting pH must be between 0 and 14.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-rank when six jars exist
        if self.test.results.count() == 6:
            self.test.rank_results()
