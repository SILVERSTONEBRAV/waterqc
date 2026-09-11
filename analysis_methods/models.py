import uuid
import json
import hashlib
import math
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from accounts.models import CustomUser  # Imported as requested
from django.utils import timezone

created_at = models.DateTimeField(default=timezone.now, blank=True, null=True)
updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)


# -------------------------
# Abstract Base Method Model
# -------------------------
class AbstractBaseMethod(models.Model):
    """
    Abstract base class for all analysis methods (chemical, microbial, etc.)
    with UUID, audit fields, versioning.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="created_%(class)s")
    updated_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="updated_%(class)s")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-updated_at"]

# -------------------------
# Chemical Analysis Method
# -------------------------
class ChemicalAnalysisMethod(AbstractBaseMethod):
    method = models.CharField(max_length=255, unique=True)
    kebs_reference = models.CharField(max_length=255, help_text="Official KEBS reference standard")
    formula = models.TextField(
        blank=True,
        help_text="Pythonic formula using variables from `inputs_structure`."
    )
    inputs_structure = models.JSONField(default=list, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    rounding_precision = models.PositiveSmallIntegerField(default=2)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    tags = models.JSONField(default=list, blank=True)
    formula_hash = models.CharField(max_length=64, editable=False, blank=True)

    class Meta:
        verbose_name = "Chemical Analysis Method"
        verbose_name_plural = "Chemical Analysis Methods"
        unique_together = ("method", "version")
        ordering = ["method", "-version"]

    def __str__(self):
        return f"{self.method} (v{self.version})"

    def clean(self):
        if self.formula:
            validate_formula_expression(self.formula)

    def get_input_fields(self):
        return [i["name"] for i in self.inputs_structure if "name" in i]

    def generate_formula_hash(self):
        raw = f"{self.method}:{self.formula}:{json.dumps(self.inputs_structure)}:{self.version}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def save(self, *args, **kwargs):
        self.formula_hash = self.generate_formula_hash()
        self.full_clean()
        super().save(*args, **kwargs)

    def evaluate(self, input_data: dict) -> float | None:
        missing = [f["name"] for f in self.inputs_structure if f.get("required") and f["name"] not in input_data]
        if missing:
            raise ValidationError(f"Missing required inputs: {missing}")

        try:
            safe_context = {
                **{key: float(input_data[key]) for key in self.get_input_fields() if key in input_data},
                "math": math
            }
            result = eval(self.formula, {"__builtins__": {}}, safe_context)
            return round(result, self.rounding_precision)
        except Exception as e:
            raise ValidationError(f"Evaluation error: {str(e)}")

    def example_input_payload(self):
        return {inp["name"]: 0.0 for inp in self.inputs_structure if "name" in inp}

    def describe_inputs(self):
        return ", ".join(f'{i["label"]} ({i["name"]})' for i in self.inputs_structure)

    def as_dict(self):
        return {
            "id": self.id,
            "method": self.method,
            "description": self.description,
            "unit": self.unit,
            "inputs_structure": self.inputs_structure,
            "formula": self.formula,
            "example_inputs": self.example_input_payload(),
            "version": self.version,
            "category": self.category,
            "tags": self.tags
        }

# -------------------------
# Microbial Method
# -------------------------
class MicrobialMethodStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', _('Active')
    DEPRECATED = 'DEPRECATED', _('Deprecated')
    UNDER_REVIEW = 'UNDER_REVIEW', _('Under Review')

class MicrobialMethod(AbstractBaseMethod):
    name = models.CharField(max_length=150)
    kebs_reference = models.CharField(max_length=255, help_text="Official KEBS reference standard")
    description = models.TextField()
    incubation_time = models.DurationField(help_text="Incubation time (hh:mm:ss)")
    confirmatory_tests = models.TextField(help_text="Comma-separated confirmatory tests")
    status = models.CharField(
        max_length=20,
        choices=MicrobialMethodStatus.choices,
        default=MicrobialMethodStatus.ACTIVE
    )
    change_log = models.TextField(blank=True)

    class Meta:
        verbose_name = "Microbial Method"
        verbose_name_plural = "Microbial Methods"
        unique_together = ("name", "version")

    def __str__(self):
        return f"{self.name} (v{self.version})"

    def get_incubation_hours(self):
        return round(self.incubation_time.total_seconds() / 3600, 2)

    def get_confirmatory_tests_list(self):
        return [test.strip() for test in self.confirmatory_tests.split(',') if test.strip()]

    def increment_version(self, user, changelog=""):
        self.version += 1
        self.change_log = changelog
        self.updated_by = user
        self.save()

    @property
    def is_deprecated(self):
        return self.status == MicrobialMethodStatus.DEPRECATED

# -------------------------
# WasteWater Analysis Method
# -------------------------
class WWAnalysisMethod(AbstractBaseMethod):
    name = models.CharField(max_length=255, unique=True)
    reference = models.CharField(max_length=255, help_text="Official reference standard")

    class Meta:
        verbose_name = "WasteWater Analysis Method"
        verbose_name_plural = "WasteWater Analysis Methods"

    def __str__(self):
        return f"{self.name} (v{self.version})"

# -------------------------
# CleanWater Analysis Method
# -------------------------
class CWAnalysisMethod(AbstractBaseMethod):
    name = models.CharField(max_length=255, unique=True)
    reference = models.CharField(max_length=255, help_text="Official reference standard")

    class Meta:
        verbose_name = "CleanWater Analysis Method"
        verbose_name_plural = "CleanWater Analysis Methods"

    def __str__(self):
        return f"{self.name} (v{self.version})"

# -------------------------
# Utility: Formula Validator (Placeholder)
# -------------------------
def validate_formula_expression(expr):
    if not isinstance(expr, str) or not expr.strip():
        raise ValidationError("Formula must be a valid non-empty string.")
