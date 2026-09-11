# xmicalconcentration/models.py

from __future__ import annotations

import ast
import operator
import uuid
from decimal import InvalidOperation
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


##############################################################################
# SAFE FORMULA EVALUATION
##############################################################################

SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def safe_eval_formula(expr: str, variables: dict):
    """
    Safely evaluate arithmetic formulas.

    Example:
        (reading * 10) + 5
    """

    def _eval(node):
        if isinstance(node, ast.Num):
            return node.n

        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.BinOp):
            op = SAFE_OPERATORS.get(type(node.op))
            if not op:
                raise ValidationError(_("Unsupported operator."))

            return op(
                _eval(node.left),
                _eval(node.right),
            )

        if isinstance(node, ast.UnaryOp):
            op = SAFE_OPERATORS.get(type(node.op))
            if not op:
                raise ValidationError(_("Unsupported operator."))

            return op(_eval(node.operand))

        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValidationError(
                    _(f"Invalid variable '{node.id}' in formula.")
                )

            return variables[node.id]

        raise ValidationError(
            _(f"Unsupported expression: {ast.dump(node)}")
        )

    try:
        parsed = ast.parse(expr, mode="eval")
        return _eval(parsed.body)

    except ValidationError:
        raise

    except Exception as exc:
        raise ValidationError(
            _(f"Formula evaluation failed: {exc}")
        )


##############################################################################
# MODEL
##############################################################################

class XmicalConcentration(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    treatment_plant = models.ForeignKey(
        "t.TreatmentPlant",
        on_delete=models.CASCADE,
        related_name="xmical_concentrations",
    )

    phase = models.ForeignKey(
        "t.TreatmentPlantPhase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="xmical_concentrations",
    )

    chemical = models.ForeignKey(
        "ca.Chemical",
        on_delete=models.CASCADE,
        related_name="xmical_concentrations",
    )

    tank = models.ForeignKey(
        "o.ChemicalTank",
        on_delete=models.CASCADE,
        related_name="xmical_concentrations",
    )

    measured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="concentration_measurements",
    )

    chemical_name = models.CharField(
        max_length=255,
        editable=False,
        db_index=True,
        help_text=_("Chemical name snapshot."),
    )

    measurement_date = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    hydrometer_reading = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        help_text=_("Hydrometer reading."),
    )

    concentration_mg_per_l = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        editable=False,
    )

    formula_used = models.TextField(
        blank=True,
        editable=False,
    )

    comments = models.TextField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_xmical_concentrations",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_xmical_concentrations",
    )

    class Meta:
        verbose_name = _("Chemical Concentration")
        verbose_name_plural = _("Chemical Concentrations")

        ordering = [
            "-measurement_date",
        ]

        indexes = [
            models.Index(
                fields=[
                    "measurement_date",
                ]
            ),
            models.Index(
                fields=[
                    "treatment_plant",
                    "measurement_date",
                ]
            ),
            models.Index(
                fields=[
                    "chemical",
                    "measurement_date",
                ]
            ),
            models.Index(
                fields=[
                    "tank",
                    "measurement_date",
                ]
            ),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "chemical",
                    "tank",
                    "measurement_date",
                ],
                name="unique_chemical_measurement_per_tank_time",
            )
        ]

    def __str__(self):
        return (
            f"{self.chemical_name} "
            f"({self.concentration_mg_per_l} mg/L)"
        )

    def get_absolute_url(self):
        return reverse(
            "xmicalconcentration_detail",
            kwargs={"pk": self.pk},
        )

    def clean(self):
        super().clean()

        if self.hydrometer_reading is None:
            raise ValidationError(
                _("Hydrometer reading is required.")
            )

        if self.hydrometer_reading <= 0:
            raise ValidationError(
                _("Hydrometer reading must be greater than zero.")
            )

    def calculate_concentration(self):
        formula = self.chemical.hydrometer_formula

        if not formula:
            raise ValidationError(
                _(
                    f"No hydrometer formula defined for "
                    f"{self.chemical.name}"
                )
            )

        try:
            reading = float(self.hydrometer_reading)

        except (ValueError, TypeError, InvalidOperation):
            raise ValidationError(
                _("Invalid hydrometer reading.")
            )

        result = safe_eval_formula(
            formula,
            {
                "reading": reading,
            },
        )

        result = round(float(result), 3)

        snapshot = (
            f"{formula}\n"
            f"reading={reading}\n"
            f"result={result}"
        )

        return result, snapshot

    def save(self, *args, **kwargs):
        self.chemical_name = self.chemical.name

        result, formula_snapshot = (
            self.calculate_concentration()
        )

        self.concentration_mg_per_l = result
        self.formula_used = formula_snapshot

        self.full_clean()

        super().save(*args, **kwargs)

    @property
    def label(self):
        return (
            f"{self.chemical_name} "
            f"({self.concentration_mg_per_l} mg/L)"
        )

    @property
    def is_recent(self):
        return (
            timezone.now() - self.measurement_date
        ).days <= 2

    @property
    def age(self):
        return timezone.now() - self.measurement_date