# ca/models.py
from __future__ import annotations

import ast
import hashlib
import json
import math
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Max, Q
from django.utils import timezone
from django_countries.fields import CountryField
from viewflow.workflow.models import Process

from CompanyInfo.models import CompanyInfo
from t.models import TreatmentPlant

from .events import batch_status_changed, checklist_completed, request_status_changed
from .utils.coa_pdf import generate_coa_pdf, generate_qr_code

def today_date():
    return timezone.now().date()

ALLOWED_MATH_FUNCS = {
    "sqrt", "log", "log10", "exp", "pow",
    "sin", "cos", "tan", "asin", "acos", "atan",
    "sinh", "cosh", "tanh", "fabs", "floor", "ceil", "pi", "e"
}

def default_received_date():
    return timezone.now().date()
def validate_formula_expression(expr: str, *, allow_math_attr: bool = True):
    """
    Validate a Python expression AST allowing only safe nodes and (optionally) math.<func> calls
    where <func> ∈ ALLOWED_MATH_FUNCS.
    """
    if not expr:
        return

    allowed_nodes = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant, ast.Name,
        ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
        ast.Call, ast.Tuple, ast.Dict, ast.Attribute, ast.Compare,
        ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.BoolOp,
        ast.And, ast.Or, ast.Subscript, ast.Slice, ast.Index
    )

    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        raise ValidationError(f"Invalid formula syntax: {e}") from e

    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValidationError(f"Disallowed expression element: {type(node).__name__}")

        # Disallow bare function calls unless they are math.<allowed>
        if isinstance(node, ast.Call):
            func = node.func
            if allow_math_attr and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if not (func.value.id == "math" and func.attr in ALLOWED_MATH_FUNCS):
                    raise ValidationError(f"Only math.<func> calls are allowed (got '{ast.unparse(func)}').")
            else:
                # Disallow Name() calls entirely (e.g., pow(...) unless via math.pow)
                raise ValidationError("Function calls must be of the form math.<allowed_func>(...).")

        # Disallow names other than the inputs and 'math'. Actual allowed variable names
        # will be enforced at evaluation time by the context, but we pre-limit here too.
        if isinstance(node, ast.Name):
            if node.id not in {"reading", "math"}:
                # Note: 'reading' is for hydrometer formulas; for method formulas we don't know inputs here,
                # but final safety is enforced by the eval context which only exposes allowed keys + math.
                pass

    return True


def safe_eval_formula(formula: str, context: dict):
    """
    Evaluate a previously validated formula with a tightly controlled context.
    - __builtins__ removed
    - Only provided context keys and math (module) available
    """
    return eval(formula, {"__builtins__": {}}, context)


# ----------------------------
# Core Models
# ----------------------------
class Chemical(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=25, unique=True, help_text="Short code for the chemical, e.g. ALUM, CL, POLY")
    description = models.TextField(blank=True)
    grade = models.CharField(max_length=100, blank=True)
    hydrometer_formula = models.TextField(
        blank=True,
        help_text="Python formula using 'reading' as the input variable. Example: (reading * 1.05 + 2)"
    )

    def clean(self):
        super().clean()
        if self.hydrometer_formula:
            formula = self.hydrometer_formula.strip()
            validate_formula_expression(formula, allow_math_attr=True)
            tree = ast.parse(formula, mode="eval")
            unknown_names = sorted({
                node.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Name)
                and node.id not in {"reading", "math"}
            })
            if unknown_names:
                raise ValidationError(
                    "The hydrometer formula references undefined variable(s): "
                    + ", ".join(unknown_names)
                )

    def calculate_hydrometer_value(self, reading):
        if reading is None:
            raise ValidationError("A hydrometer reading is required.")
        try:
            value = float(reading)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Hydrometer reading must be numeric.") from exc
        if not math.isfinite(value):
            raise ValidationError("Hydrometer reading must be finite.")
        if not self.hydrometer_formula:
            return value
        formula = self.hydrometer_formula.strip()
        self.clean()
        result = safe_eval_formula(formula, {"reading": value, "math": math})
        if isinstance(result, bool):
            raise ValidationError("The hydrometer formula must return a numeric value.")
        try:
            result = float(result)
        except (TypeError, ValueError) as exc:
            raise ValidationError("The hydrometer formula must return a numeric value.") from exc
        if not math.isfinite(result):
            raise ValidationError("The hydrometer formula produced a non-finite result.")
        return result

    def apply_hydrometer_formula(self, reading):
        return self.calculate_hydrometer_value(reading)

    def __str__(self):
        return f"{self.code} - {self.name}"


def validate_contract_document(value):
    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
    extension = value.name.lower().rsplit(".", 1)[-1] if "." in value.name else ""

    if f".{extension}" not in allowed_extensions:
        raise ValidationError(
            "Contract document must be a PDF or an image file "
            "(JPG, JPEG, PNG, or WEBP)."
        )


class Supplier(models.Model):
    name = models.CharField(max_length=100)
    contract_number = models.CharField(
        max_length=100,
        unique=True,
    )
    contract_document = models.FileField(
        upload_to="chemical/supplier_contracts/%Y/%m/",
        validators=[validate_contract_document],
        blank=True,
        null=True,
    )
    contact_info = models.TextField(blank=True)

    def __str__(self):
        return self.name

class ChemicalLocation(models.Model):
    name = models.CharField(
        max_length=100,
    )

    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.SET_NULL,
        null=True,
        related_name="chemical_locations",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "treatment_plant"],
                name="ca_unique_location_plant",
            ),
        ]
        indexes = [
            models.Index(
                fields=["treatment_plant"],
                name="ca_loc_plant_idx",
            ),
            models.Index(
                fields=["name"],
                name="ca_loc_name_idx",
            ),
        ]

    def __str__(self):
        return self.name




class ChemicalSpecification(models.Model):
    chemical = models.ForeignKey(Chemical, on_delete=models.CASCADE, related_name="specifications")
    parameter_name = models.CharField(max_length=100)
    unit = models.CharField(max_length=20)
    method = models.ForeignKey("analysis_methods.ChemicalAnalysisMethod", on_delete=models.SET_NULL,null=True )
    min_limit = models.FloatField(null=True, blank=True)
    max_limit = models.FloatField(null=True, blank=True)
    is_required = models.BooleanField(default=True)
    version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    treatment_plant = models.ForeignKey(TreatmentPlant, on_delete=models.CASCADE, related_name="chemical_specifications")

    class Meta:
        unique_together = ('chemical', 'parameter_name', 'version', 'treatment_plant')
        ordering = ['chemical__name', 'parameter_name']

    def __str__(self):
        return f"{self.chemical.name} - {self.parameter_name} (v{self.version})"


class ChemicalSpecificationRemark(models.Model):
    specification = models.ForeignKey(ChemicalSpecification, on_delete=models.CASCADE, related_name='remarks')
    on_pass = models.TextField()
    on_fail = models.TextField()

    def __str__(self):
        return f"Remarks for {self.specification}"


class PackagingStatus(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ChemicalCertApprover(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    signature = models.ImageField(upload_to='approvers/signatures/', null=True, blank=True)
    rubber_stamp = models.ImageField(upload_to='approvers/stamps/', null=True, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username




class ChemicalBatch(models.Model):
    class Status(models.TextChoices):
        RECEIVED = 'RECEIVED', 'Received'
        ANALYSED = 'ANALYSED', 'Analysed'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        UTILIZED = 'UTILIZED', 'Utilized in Treatment'
        RETURNED = 'RETURNED', 'Return to Supplier (RTS)'

    sample_id = models.CharField(max_length=50, unique=True, editable=False)
    delivery_note_number = models.CharField(max_length=100, unique=True, blank=True)
    batch_number = models.CharField(max_length=100, unique=True)
    chemical = models.ForeignKey("Chemical", on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier,on_delete=models.PROTECT,related_name="chemical_batches",related_query_name="chemical_batches",)
    treatment_plant = models.ForeignKey("t.TreatmentPlant", on_delete=models.SET_NULL, null=True,related_name='chemical_batches')
    received_date = models.DateField(null=True, auto_now_add=True)
    quantity_received = models.FloatField()
    unit = models.CharField(max_length=10, default='kg')
    package_count = models.PositiveIntegerField(null=True,blank=True,help_text=(
            "Total number of discrete packages, bags, drums, "
            "containers, or other sampling units in the batch."),
    )
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,related_name='received_batches')
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.RECEIVED)
    coa_generated = models.BooleanField(default=False)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Allowed transitions
    batch_transitions = {
        Status.RECEIVED: [Status.ANALYSED, Status.REJECTED],
        Status.ANALYSED: [Status.APPROVED, Status.REJECTED],
        Status.APPROVED: [Status.UTILIZED, Status.RETURNED],
        Status.REJECTED: [Status.RETURNED],
        Status.UTILIZED: [],
        Status.RETURNED: [],
    }

    def clean(self):
        super().clean()
        errors = {}
        if self.quantity_received is None or self.quantity_received <= 0:
            errors["quantity_received"] = "Quantity received must be greater than zero."
        elif not math.isfinite(float(self.quantity_received)):
            errors["quantity_received"] = "Quantity received must be finite."
        if self.package_count is not None and self.package_count < 1:
            errors["package_count"] = "Package count must be at least one."
        if self.treatment_plant_id is None:
            errors["treatment_plant"] = "A treatment plant is required."
        if errors:
            raise ValidationError(errors)

    # -------------------------
    # Auto-generate sample_id
    # -------------------------
    def save(self, *args, **kwargs):
        if not self.sample_id:
            year = timezone.now().strftime("%Y")

            # Chemical prefix
            chemical_prefix = (
                self.chemical.code.upper()
                if hasattr(self.chemical, "code") and self.chemical.code
                else self.chemical.name[:4].upper()
            )

            # Plant prefix
            plant_prefix = (
                self.treatment_plant.code.upper()
                if self.treatment_plant and hasattr(self.treatment_plant, "code") and self.treatment_plant.code
                else (self.treatment_plant.name[:3].upper() if self.treatment_plant else "PLT")
            )

            prefix = f"{chemical_prefix}-{plant_prefix}-{year}"

            last_id = (
                ChemicalBatch.objects.filter(sample_id__startswith=prefix)
                .aggregate(max_id=Max("sample_id"))["max_id"]
            )
            new_seq = int(last_id.split("-")[-1]) + 1 if last_id else 1
            self.sample_id = f"{prefix}-{new_seq:03d}"

        # Validate quantity
        if self.quantity_received <= 0:
            raise ValidationError("Quantity received must be positive.")

        super().save(*args, **kwargs)

    # -------------------------
    # Transitions
    # -------------------------
    def transition_to(self, target_status: str, performed_by=None, auto=False):
        if not self.can_transition_to(target_status):
            raise ValidationError(f"Invalid transition: {self.status} → {target_status}")

        if target_status == self.Status.APPROVED:
            if hasattr(self, "test_results"):
                results = self.test_results.all()
                if results.filter(Q(status__isnull=True) | Q(status="")).exists():
                    raise ValidationError("Cannot approve: pending test results exist.")
                if results.filter(status=BatchTestResult.Status.FAIL).exists():
                    raise ValidationError("Cannot approve: one or more test results failed.")

        old_status = self.status
        self.status = target_status
        self.save(update_fields=["status"])

        batch_status_changed.send(
            sender=self.__class__,
            instance=self,
            old_status=old_status,
            new_status=target_status,
            performed_by=performed_by if performed_by else "SYSTEM" if auto else None
        )

    # -------------------------
    # Helper Methods
    # -------------------------
    def can_transition_to(self, target_status: str):
        return target_status in self.batch_transitions.get(self.status, [])

    def is_approved(self):
        return self.status == self.Status.APPROVED

    def __str__(self):
        return f"Batch {self.sample_id} - {self.chemical.name} [{self.status}]"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sample_id"], name="unique_sample_id")
        ]
        ordering = ["-received_date", "-created_at"]
        verbose_name = "Batch"
        verbose_name_plural = "Batches"

class ChemicalAnalysisRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"

    REQUEST_DEADLINE_HOURS = 9
    CHEMICAL_ANALYSIS_TASK_NAME = "Water Treatment Chemical Analysis"

    request_id = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        editable=False,
    )

    batch = models.OneToOneField(
        ChemicalBatch,
        on_delete=models.CASCADE,
        related_name="analysis_request",
        null=True,
        blank=True,
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chemical_requests",
    )

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_analysis_requests",
    )

    delivery_date = models.DateField()

    location = models.ForeignKey(
        ChemicalLocation,
        on_delete=models.PROTECT,
        related_name="analysis_requests",
    )

    analysis_started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    analysis_deadline = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_chemical_requests",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    ASSIGNMENT_TIMEOUT_MINUTES = 30

    assignment_due_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Time after which the system may automatically assign "
            "the scheduled chemical-analysis analysts if no manual "
            "assignment has been made."
        ),
    )

    auto_assigned_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    manual_assigned_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    assigned_analysts = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="assigned_requests",
        blank=True,
        editable=True,
    )

    request_transitions = {
        Status.PENDING: (
            Status.IN_PROGRESS,
        ),
        Status.IN_PROGRESS: (
            Status.COMPLETED,
        ),
        Status.COMPLETED: (),
    }

    request_to_batch_cascade = {
        Status.PENDING: None,
        Status.IN_PROGRESS: None,
        Status.COMPLETED: ChemicalBatch.Status.ANALYSED,
    }

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "-created_at"],
                name="ca_req_status_created_idx",
            ),
            models.Index(
                fields=["analysis_deadline", "status"],
                name="ca_req_deadline_status_idx",
            ),
            models.Index(
                fields=["delivery_date", "-created_at"],
                name="ca_req_delivery_created_idx",
            ),
            models.Index(
                fields=["batch", "status"],
                name="ca_req_batch_status_idx",
            ),
        ]

    @property
    def chemical(self):
        if not self.batch_id:
            return None
        return self.batch.chemical

    @property
    def supplier(self):
        if not self.batch_id:
            return None
        return self.batch.supplier

    @property
    def treatment_plant(self):
        if not self.batch_id:
            return None
        return self.batch.treatment_plant

    @property
    def quantity(self):
        if not self.batch_id:
            return None
        return self.batch.quantity_received

    @property
    def unit(self):
        if not self.batch_id:
            return None
        return self.batch.unit

    @property
    def sample_id(self):
        if not self.batch_id:
            return None
        return self.batch.sample_id

    @property
    def batch_number(self):
        if not self.batch_id:
            return None
        return self.batch.batch_number

    @property
    def is_pending(self):
        return self.status == self.Status.PENDING

    @property
    def is_in_progress(self):
        return self.status == self.Status.IN_PROGRESS

    @property
    def is_completed(self):
        return self.status == self.Status.COMPLETED

    @property
    def is_overdue(self):
        return bool(
            self.status != self.Status.COMPLETED
            and self.analysis_deadline
            and timezone.now() > self.analysis_deadline
        )

    @property
    def time_remaining(self):
        if self.status == self.Status.COMPLETED:
            return timedelta(0)

        if not self.analysis_deadline:
            return None

        return self.analysis_deadline - timezone.now()

    @property
    def assigned_analyst_count(self):
        return self.assigned_analysts.count()

    @property
    def has_assigned_analysts(self):
        return self.assigned_analysts.exists()

    @property
    def assignment_pending(self):
        return (
            self.status == self.Status.PENDING
            and not self.has_assigned_analysts
        )

    @property
    def assignment_overdue(self):
        return (
            self.assignment_pending
            and self.assignment_due_at is not None
            and timezone.now() >= self.assignment_due_at
        )

    @property
    def latest_checklist(self):
        return (
            self.checklists
            .select_related(
                "chemical",
                "sampled_by",
                "requested_by",
            )
            .order_by("-created_at")
            .first()
        )

    def get_current_assigned_analysts(self):
        """Return analysts currently scheduled for this task.

        This method only discovers the roster. It never changes the
        request's manual assignments.
        """
        if not self.batch_id:
            return get_user_model().objects.none()

        from weeklytasks.models import DailyTaskAssignment, WeeklyDutyTask

        now = timezone.localtime()
        current_date = now.date()
        current_time = now.time()

        plant_id = self.batch.treatment_plant_id
        if not plant_id:
            return get_user_model().objects.none()

        section_id = getattr(self.batch, "section_id", None)
        if not section_id:
            return get_user_model().objects.none()

        task = (
            WeeklyDutyTask.objects
            .filter(
                task_template__name__iexact=self.CHEMICAL_ANALYSIS_TASK_NAME,
                task_template__is_active=True,
                treatment_plant_id=plant_id,
                section_id=section_id,
                week__start_date__lte=current_date,
                week__end_date__gte=current_date,
            )
            .order_by("-week__start_date", "-created_at")
            .first()
        )

        if not task:
            return get_user_model().objects.none()

        assignments = (
            DailyTaskAssignment.objects
            .filter(
                task=task,
                date=current_date,
                user__is_active=True,
                user__assigned_treatment_plant_id=plant_id,
                user__section_id=section_id,
                shift__is_deleted=False,
                shift__start_time__lte=current_time,
                shift__end_time__gt=current_time,
            )
            .values_list("user_id", flat=True)
            .distinct()
        )

        return (
            get_user_model().objects
            .filter(
                pk__in=assignments,
                is_active=True,
                assigned_treatment_plant_id=plant_id,
                section_id=section_id,
            )
            .order_by("last_name", "first_name", "username")
        )

    def assign_analysts(self, users, *, assigned_by=None, manual=True):
        """Assign analysts explicitly without allowing later auto-assignment
        to overwrite the selection.
        """
        users = list(users or [])

        if not users:
            raise ValidationError(
                "At least one active analyst must be assigned."
            )

        user_ids = []
        User = get_user_model()

        for user in users:
            user_id = getattr(user, "pk", user)
            if not user_id:
                raise ValidationError("Every analyst must be a valid user.")

            user_obj = (
                user
                if getattr(user, "pk", None)
                else User.objects.filter(pk=user_id).first()
            )

            if user_obj is None:
                raise ValidationError(
                    f"Analyst {user_id} could not be found."
                )

            if not user_obj.is_active:
                raise ValidationError(
                    f"{user_obj.get_username()} is inactive and cannot be assigned."
                )

            if (
                self.batch_id
                and self.batch.treatment_plant_id
                and getattr(user_obj, "assigned_treatment_plant_id", None)
                != self.batch.treatment_plant_id
            ):
                raise ValidationError(
                    f"{user_obj.get_username()} is not assigned to the "
                    "treatment plant for this chemical batch."
                )

            user_ids.append(user_obj.pk)

        now = timezone.now()
        self.assigned_analysts.set(sorted(set(user_ids)))

        if manual:
            self.manual_assigned_at = now
            self.auto_assigned_at = None
            type(self).objects.filter(pk=self.pk).update(
                manual_assigned_at=now,
                auto_assigned_at=None,
                updated_at=now,
            )

        return self.assigned_analysts.all()

    def clear_analyst_assignments(self, *, allow_reassignment=False):
        if self.status != self.Status.PENDING and not allow_reassignment:
            raise ValidationError(
                "Analysts can only be cleared while the request is pending."
            )

        self.assigned_analysts.clear()

        now = timezone.now()
        type(self).objects.filter(pk=self.pk).update(
            manual_assigned_at=None,
            auto_assigned_at=None,
            updated_at=now,
        )

        self.manual_assigned_at = None
        self.auto_assigned_at = None
        return self

    def auto_assign_analysts_if_due(self, *, now=None):
        """Automatically assign the scheduled analysts after 30 minutes.

        Manual assignments always take precedence. The method is idempotent
        and safe to call repeatedly from a periodic Celery task.
        """
        if not self.pk:
            return get_user_model().objects.none()

        now = now or timezone.now()

        with transaction.atomic():
            request = (
                type(self).objects
                .select_for_update()
                .get(pk=self.pk)
            )

            if request.status != type(self).Status.PENDING:
                return request.assigned_analysts.all()

            if request.assigned_analysts.exists():
                return request.assigned_analysts.all()

            if (
                request.assignment_due_at is None
                or now < request.assignment_due_at
            ):
                return request.assigned_analysts.all()

            analysts = request.get_current_assigned_analysts()

            if not analysts.exists():
                return request.assigned_analysts.all()

            request.assigned_analysts.set(
                analysts.values_list("pk", flat=True)
            )

            request.auto_assigned_at = now
            request.save(
                update_fields=[
                    "auto_assigned_at",
                    "updated_at",
                ]
            )

            return request.assigned_analysts.all()

    def populate_assigned_analysts(self):
        """Backward-compatible entry point.

        It intentionally performs no immediate assignment. Automatic
        assignment is only permitted once the 30-minute deadline expires.
        """
        return self.auto_assign_analysts_if_due()

    def is_assigned_analyst(self, user):
        if user is None or not getattr(user, "is_active", False):
            return False

        return self.assigned_analysts.filter(pk=user.pk).exists()

    def clean(self):
        super().clean()

        errors = {}

        if self.batch_id:
            batch = self.batch

            if batch is None:
                errors["batch"] = (
                    "The selected chemical batch could not be found."
                )
            else:
                if (
                    self.location_id
                    and batch.treatment_plant_id
                    and self.location.treatment_plant_id
                    and batch.treatment_plant_id
                    != self.location.treatment_plant_id
                ):
                    errors["location"] = (
                        "The analysis location must belong to the "
                        "same treatment plant as the chemical batch."
                    )

                if (
                    self.status in (
                        self.Status.IN_PROGRESS,
                        self.Status.COMPLETED,
                    )
                    and not batch.chemical_id
                ):
                    errors["batch"] = (
                        "The chemical batch must have an associated "
                        "chemical before analysis can proceed."
                    )

        if self.received_by_id:
            if not self.received_by.is_active:
                errors["received_by"] = (
                    "The staff member receiving the analysis request "
                    "must be active."
                )
            elif self.pk and not self.assigned_analysts.filter(
                pk=self.received_by_id
            ).exists():
                errors["received_by"] = (
                    "The staff member receiving the chemical analysis "
                    "request must be one of the assigned analysts."
                )

        if (
            self.status in (
                self.Status.IN_PROGRESS,
                self.Status.COMPLETED,
            )
            and not self.analysis_started_at
        ):
            errors["analysis_started_at"] = (
                "An analysis start time is required."
            )

        if self.status == self.Status.IN_PROGRESS:
            if not self.analysis_deadline:
                errors["analysis_deadline"] = (
                    "An analysis deadline is required while "
                    "analysis is in progress."
                )

            if self.completed_at:
                errors["completed_at"] = (
                    "An in-progress request cannot have a completion time."
                )

            if self.completed_by_id:
                errors["completed_by"] = (
                    "An in-progress request cannot have a completing user."
                )

        if self.status == self.Status.COMPLETED:
            if not self.completed_at:
                errors["completed_at"] = (
                    "A completed request must have a completion time."
                )

            if not self.completed_by_id:
                errors["completed_by"] = (
                    "A completed request must have a completing user."
                )

        if (
            self.assignment_due_at
            and self.created_at
            and self.assignment_due_at < self.created_at
        ):
            errors["assignment_due_at"] = (
                "The analyst-assignment deadline cannot be earlier "
                "than the request creation time."
            )

        if (
            self.analysis_started_at
            and self.analysis_deadline
            and self.analysis_deadline < self.analysis_started_at
        ):
            errors["analysis_deadline"] = (
                "The analysis deadline cannot be earlier than "
                "the analysis start time."
            )

        if (
            self.completed_at
            and self.analysis_started_at
            and self.completed_at < self.analysis_started_at
        ):
            errors["completed_at"] = (
                "The completion time cannot be earlier than "
                "the analysis start time."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.request_id:
            delivery_date = (
                self.delivery_date
                or timezone.now().date()
            )
            self.request_id = (
                f"REQ-"
                f"{delivery_date.strftime('%Y%m%d')}-"
                f"{uuid.uuid4().hex[:8].upper()}"
            )

        if self.assignment_due_at is None:
            self.assignment_due_at = (
                timezone.now()
                + timedelta(minutes=self.ASSIGNMENT_TIMEOUT_MINUTES)
            )

        super().save(*args, **kwargs)

        if self.received_by_id and self.pk:
            if not self.assigned_analysts.filter(
                pk=self.received_by_id
            ).exists():
                raise ValidationError(
                    "The staff member receiving the chemical analysis "
                    "request must be one of the assigned analysts."
                )

    def can_transition_to(self, target_status):
        return target_status in self.request_transitions.get(
            self.status,
            (),
        )

    def _validate_start_requirements(self):
        if not self.batch_id:
            raise ValidationError(
                "Cannot start analysis without an associated "
                "chemical batch."
            )

        if not self.location_id:
            raise ValidationError(
                "Cannot start analysis without an analysis location."
            )

        if not self.assigned_analysts.exists():
            raise ValidationError(
                "No analyst is currently assigned to perform "
                "Water Treatment Chemical Analysis for this "
                "treatment plant, section, date, and shift."
            )

        if self.received_by_id and not self.is_assigned_analyst(
            self.received_by
        ):
            raise ValidationError(
                "The staff member receiving the chemical analysis "
                "request is not one of the currently assigned analysts."
            )

        if not self.batch.chemical_id:
            raise ValidationError(
                "The chemical batch must have an associated chemical."
            )

    def _validate_completion_requirements(self):
        if not self.batch_id:
            raise ValidationError(
                "Cannot complete an analysis request without "
                "an associated chemical batch."
            )

        if not self.analysis_started_at:
            raise ValidationError(
                "Cannot complete an analysis request that "
                "has not been started."
            )

        if not self.assigned_analysts.exists():
            raise ValidationError(
                "At least one analyst must currently be assigned "
                "to the chemical analysis task."
            )

        results = self.batch.test_results.select_related(
            "parameter",
            "parameter__chemical",
        )

        if not results.exists():
            raise ValidationError(
                "Cannot complete the analysis request without "
                "analytical test results."
            )

        required_specifications = (
            ChemicalSpecification.objects.filter(
                chemical_id=self.batch.chemical_id,
                treatment_plant_id=self.batch.treatment_plant_id,
                is_required=True,
            )
        )

        if required_specifications.exists():
            completed_parameter_ids = set(
                results.exclude(
                    status=BatchTestResult.Status.NA
                ).values_list(
                    "parameter_id",
                    flat=True,
                )
            )

            missing = required_specifications.exclude(
                pk__in=completed_parameter_ids
            )

            if missing.exists():
                names = list(
                    missing.values_list(
                        "parameter_name",
                        flat=True,
                    )[:10]
                )

                raise ValidationError(
                    "Cannot complete the analysis because the "
                    "following required parameters have no applicable "
                    f"results: {', '.join(names)}."
                )

        if results.filter(
            status__isnull=True
        ).exists():
            raise ValidationError(
                "All analytical test results must have a status "
                "before the request can be completed."
            )

    def transition_to(
        self,
        target_status,
        performed_by=None,
        auto=False,
    ):
        if target_status not in self.Status.values:
            raise ValidationError(
                f"Unknown analysis request status: {target_status}"
            )

        with transaction.atomic():
            request = (
                type(self).objects
                .select_for_update()
                .select_related(
                    "batch",
                    "location",
                )
                .get(pk=self.pk)
            )

            old_status = request.status

            if target_status == old_status:
                raise ValidationError(
                    f"Analysis request is already {old_status}."
                )

            if target_status not in request.request_transitions.get(
                old_status,
                (),
            ):
                raise ValidationError(
                    f"Invalid transition: "
                    f"{old_status} → {target_status}"
                )

            now = timezone.now()

            if (
                old_status == self.Status.PENDING
                and target_status == self.Status.IN_PROGRESS
            ):
                request._validate_start_requirements()

                request.analysis_started_at = now
                request.analysis_deadline = (
                    now
                    + timedelta(
                        hours=self.REQUEST_DEADLINE_HOURS
                    )
                )

            elif (
                old_status == self.Status.IN_PROGRESS
                and target_status == self.Status.COMPLETED
            ):
                request._validate_completion_requirements()

                request.completed_at = now
                request.completed_by = performed_by

                if not request.analysis_started_at:
                    request.analysis_started_at = now

                if not request.analysis_deadline:
                    request.analysis_deadline = (
                        request.analysis_started_at
                        + timedelta(
                            hours=self.REQUEST_DEADLINE_HOURS
                        )
                    )

            request.status = target_status

            request.save(
                update_fields=[
                    "status",
                    "analysis_started_at",
                    "analysis_deadline",
                    "completed_at",
                    "completed_by",
                    "updated_at",
                ]
            )

            target_batch_status = (
                request.request_to_batch_cascade.get(
                    target_status
                )
            )

            batch = request.batch

            if (
                target_batch_status
                and batch
                and batch.status != target_batch_status
            ):
                if not batch.can_transition_to(
                    target_batch_status
                ):
                    raise ValidationError(
                        f"Cannot transition batch "
                        f"{batch.sample_id} from "
                        f"{batch.status} to "
                        f"{target_batch_status}."
                    )

                batch.transition_to(
                    target_batch_status,
                    performed_by=performed_by,
                    auto=True,
                )

            self.status = request.status
            self.analysis_started_at = (
                request.analysis_started_at
            )
            self.analysis_deadline = (
                request.analysis_deadline
            )
            self.completed_at = request.completed_at
            self.completed_by_id = request.completed_by_id
            self.updated_at = request.updated_at

            transaction.on_commit(
                lambda request_id=request.pk,
                old_status=old_status,
                new_status=target_status,
                performed_by=performed_by,
                auto=auto: request_status_changed.send(
                    sender=type(self),
                    instance=type(self).objects.get(
                        pk=request_id
                    ),
                    old_status=old_status,
                    new_status=new_status,
                    performed_by=(
                        performed_by
                        if performed_by
                        else "SYSTEM"
                        if auto
                        else None
                    ),
                )
            )

        return self

    def start_analysis(self, performed_by=None):
        return self.transition_to(
            self.Status.IN_PROGRESS,
            performed_by=performed_by,
            auto=True,
        )

    def mark_completed(self, performed_by=None):
        if performed_by is None:
            raise ValidationError(
                "A user is required to complete the analysis request."
            )

        return self.transition_to(
            self.Status.COMPLETED,
            performed_by=performed_by,
            auto=False,
        )

    def get_latest_checklist(self):
        return (
            self.checklists
            .select_related(
                "chemical",
                "sampled_by",
                "requested_by",
            )
            .order_by("-created_at")
            .first()
        )

    def get_checklists(self):
        return self.checklists.select_related(
            "chemical",
            "sampled_by",
            "requested_by",
        ).order_by("-created_at")

    def get_test_results(self):
        if not self.batch_id:
            return BatchTestResult.objects.none()

        return (
            self.batch.test_results
            .select_related(
                "parameter",
                "parameter__chemical",
                "parameter__method",
                "analyst",
            )
            .order_by(
                "parameter__chemical__name",
                "parameter__parameter_name",
                "id",
            )
        )

    def get_required_specifications(self):
        if not self.batch_id:
            return ChemicalSpecification.objects.none()

        return (
            ChemicalSpecification.objects
            .filter(
                chemical_id=self.batch.chemical_id,
                treatment_plant_id=self.batch.treatment_plant_id,
                is_required=True,
            )
            .select_related(
                "chemical",
                "method",
            )
            .prefetch_related("remarks")
            .order_by(
                "parameter_name",
                "version",
            )
        )

    def get_missing_required_specifications(self):
        if not self.batch_id:
            return ChemicalSpecification.objects.none()

        required = self.get_required_specifications()

        result_parameter_ids = self.batch.test_results.filter(
            status__in=[
                BatchTestResult.Status.PASS,
                BatchTestResult.Status.FAIL,
            ]
        ).values_list(
            "parameter_id",
            flat=True,
        )

        return required.exclude(
            pk__in=result_parameter_ids
        )

    def has_test_results(self):
        return bool(
            self.batch_id
            and self.batch.test_results.exists()
        )

    def has_failed_results(self):
        return bool(
            self.batch_id
            and self.batch.test_results.filter(
                status=BatchTestResult.Status.FAIL
            ).exists()
        )

    def has_not_applicable_results(self):
        return bool(
            self.batch_id
            and self.batch.test_results.filter(
                status=BatchTestResult.Status.NA
            ).exists()
        )

    def has_incomplete_results(self):
        if not self.batch_id:
            return True

        return self.get_missing_required_specifications().exists()

    def get_result_counts(self):
        if not self.batch_id:
            return {
                "total": 0,
                "pass": 0,
                "fail": 0,
                "na": 0,
            }

        queryset = self.batch.test_results

        return {
            "total": queryset.count(),
            "pass": queryset.filter(
                status=BatchTestResult.Status.PASS
            ).count(),
            "fail": queryset.filter(
                status=BatchTestResult.Status.FAIL
            ).count(),
            "na": queryset.filter(
                status=BatchTestResult.Status.NA
            ).count(),
        }

    def can_generate_coa(self):
        if self.status != self.Status.COMPLETED:
            return False

        if not self.batch_id:
            return False

        if not self.has_test_results():
            return False

        if self.has_incomplete_results():
            return False

        return True

    def get_or_create_coa(self):
        if not self.can_generate_coa():
            raise ValidationError(
                "A CoA can only be generated after the chemical "
                "analysis request has been completed with all "
                "required analytical results."
            )

        with transaction.atomic():
            batch = (
                ChemicalBatch.objects
                .select_for_update()
                .get(pk=self.batch_id)
            )

            coa, created = ChemicalCoA.objects.get_or_create(
                batch=batch,
            )

            if created:
                coa.auto_populate()

            return coa, created

    def mark_overdue(self):
        if self.status == self.Status.COMPLETED:
            return False

        if not self.analysis_deadline:
            return False

        return timezone.now() > self.analysis_deadline

    def refresh_from_db(
        self,
        using=None,
        fields=None,
        from_queryset=None,
    ):
        super().refresh_from_db(
            using=using,
            fields=fields,
            from_queryset=from_queryset,
        )

        return self

    def __str__(self):
        chemical_name = (
            self.chemical.name
            if self.chemical
            else "Unknown Chemical"
        )

        sample_id = (
            self.sample_id
            or "N/A"
        )

        return (
            f"Analysis Request {self.request_id} - "
            f"{chemical_name} ({sample_id})"
        )

class ChecklistForWaterTreatmentChemicalAnalysis(models.Model):
    class Grade(models.TextChoices):
        STANDARD = "STANDARD", "Standard"
        PREMIUM = "PREMIUM", "Premium"
        NA = "NA", "Not Applicable"

    chemical_analysis_request = models.ForeignKey(
        "ChemicalAnalysisRequest",
        on_delete=models.CASCADE,
        related_name="checklists",
        db_index=True,
    )

    chemical = models.ForeignKey(
        "Chemical",
        on_delete=models.PROTECT,
        related_name="chemical_analysis_checklists",
    )

    manufacturer_name_indicated = models.BooleanField(
        default=False,
    )

    chemical_name_on_label = models.BooleanField(
        default=False,
    )

    min_mass_indicated = models.BooleanField(
        default=False,
    )

    grade = models.CharField(
        max_length=20,
        choices=Grade.choices,
        default=Grade.NA,
    )

    manufacture_date = models.DateField()

    expiry_date = models.DateField()

    storage_conditions = models.CharField(
        max_length=255,
    )

    net_weight = models.DecimalField(
        max_digits=12,
        decimal_places=3,
    )

    country_of_origin = CountryField(
        default="KE",
    )

    handling_instructions = models.TextField(
        blank=True,
    )

    is_oxidizing = models.BooleanField(
        default=False,
    )

    is_corrosive = models.BooleanField(
        default=False,
    )

    may_cause_fire = models.BooleanField(
        default=False,
    )

    contact_with_acids_liberates_toxic_gas = models.BooleanField(
        default=False,
    )

    causes_burns = models.BooleanField(
        default=False,
    )

    keep_out_of_reach_of_children = models.BooleanField(
        default=False,
    )

    contact_with_eyes_action = models.BooleanField(
        default=False,
    )

    fire_action_requires_respiratory_equipment = models.BooleanField(
        default=False,
    )

    sampled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chemical_checklists_sampled",
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chemical_checklists_requested",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    completed = models.BooleanField(
        default=False,
        db_index=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_chemical_checklists",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=[
                    "chemical_analysis_request",
                    "-created_at",
                ],
                name="ca_check_req_created_idx",
            ),
            models.Index(
                fields=[
                    "completed",
                    "-created_at",
                ],
                name="ca_check_completed_idx",
            ),
            models.Index(
                fields=[
                    "chemical",
                    "-created_at",
                ],
                name="ca_check_chemical_created_idx",
            ),
            models.Index(
                fields=[
                    "expiry_date",
                    "completed",
                ],
                name="ca_check_expiry_completed_idx",
            ),
        ]

    @property
    def batch(self):
        request = self.chemical_analysis_request

        if request is None or not request.batch_id:
            return None

        return request.batch

    @property
    def sample_id(self):
        batch = self.batch
        return batch.sample_id if batch else None

    @property
    def batch_number(self):
        batch = self.batch
        return batch.batch_number if batch else None

    @property
    def treatment_plant(self):
        batch = self.batch
        return batch.treatment_plant if batch else None

    @property
    def analysis_status(self):
        request = self.chemical_analysis_request
        return request.status if request else None

    @property
    def is_expired(self) -> bool:
        if not self.expiry_date:
            return False

        return self.expiry_date < timezone.localdate()

    @property
    def is_valid_at_receipt(self):
        if not self.manufacture_date or not self.expiry_date:
            return False

        return (
            self.manufacture_date <= self.expiry_date
            and self.expiry_date >= timezone.localdate()
        )

    @property
    def is_completed(self):
        return self.completed

    @property
    def completion_status(self):
        return "COMPLETED" if self.completed else "PENDING"

    @property
    def days_until_expiry(self):
        if not self.expiry_date:
            return None

        return (
            self.expiry_date - timezone.localdate()
        ).days

    @property
    def expiry_status(self):
        if not self.expiry_date:
            return "UNKNOWN"

        if self.expiry_date < timezone.localdate():
            return "EXPIRED"

        if self.expiry_date == timezone.localdate():
            return "EXPIRES_TODAY"

        days = self.days_until_expiry

        if days is not None and days <= 30:
            return "EXPIRING_SOON"

        return "VALID"

    def _get_request(self):
        if not self.chemical_analysis_request_id:
            return None

        try:
            return (
                ChemicalAnalysisRequest.objects
                .select_related(
                    "batch",
                    "batch__chemical",
                    "batch__treatment_plant",
                    "location",
                    "location__treatment_plant",
                )
                .get(
                    pk=self.chemical_analysis_request_id
                )
            )
        except ChemicalAnalysisRequest.DoesNotExist:
            return None

    def _get_batch(self, request=None):
        request = request or self._get_request()

        if request is None or not request.batch_id:
            return None

        return request.batch

    def clean(self):
        super().clean()

        errors = {}

        request = self._get_request()
        batch = self._get_batch(request)

        if not self.chemical_analysis_request_id:
            errors["chemical_analysis_request"] = (
                "An analysis request is required."
            )
        elif request is None:
            errors["chemical_analysis_request"] = (
                "The selected analysis request could not be found."
            )

        if request is not None and not request.batch_id:
            errors["chemical_analysis_request"] = (
                "The analysis request must have an associated "
                "chemical batch."
            )

        if request is not None and batch is None:
            errors["chemical_analysis_request"] = (
                "The associated chemical batch could not be found."
            )

        if not self.chemical_id:
            errors["chemical"] = "A chemical is required."

        if batch is not None:
            if (
                self.chemical_id
                and batch.chemical_id
                and self.chemical_id != batch.chemical_id
            ):
                errors["chemical"] = (
                    "The checklist chemical must match the "
                    "chemical associated with the batch."
                )

            if (
                request is not None
                and request.location_id
                and batch.treatment_plant_id
                and request.location
                and request.location.treatment_plant_id
                and (
                    request.location.treatment_plant_id
                    != batch.treatment_plant_id
                )
            ):
                errors["chemical_analysis_request"] = (
                    "The checklist request location must belong "
                    "to the same treatment plant as the batch."
                )

        if (
            self.manufacture_date
            and self.expiry_date
            and self.expiry_date < self.manufacture_date
        ):
            errors["expiry_date"] = (
                "The expiry date cannot be earlier than "
                "the manufacture date."
            )

        if (
            self.net_weight is None
            or self.net_weight <= Decimal("0")
        ):
            errors["net_weight"] = (
                "Net weight must be greater than zero."
            )

        if (
            not isinstance(self.storage_conditions, str)
            or not self.storage_conditions.strip()
        ):
            errors["storage_conditions"] = (
                "Storage conditions are required."
            )

        if self.completed:
            if not self.completed_at:
                errors["completed_at"] = (
                    "A completion time is required for "
                    "a completed checklist."
                )

            if not self.completed_by_id:
                errors["completed_by"] = (
                    "A completing user is required for "
                    "a completed checklist."
                )
        else:
            if self.completed_at:
                errors["completed_at"] = (
                    "An incomplete checklist cannot have "
                    "a completion time."
                )

            if self.completed_by_id:
                errors["completed_by"] = (
                    "An incomplete checklist cannot have "
                    "a completing user."
                )

        if errors:
            raise ValidationError(errors)

    def validate_completion_requirements(
        self,
        request=None,
        batch=None,
    ):
        errors = {}

        request = request or self._get_request()

        if request is None:
            errors["chemical_analysis_request"] = (
                "The associated analysis request could not be found."
            )
        else:
            if not request.batch_id:
                errors["chemical_analysis_request"] = (
                    "The analysis request must have an associated "
                    "chemical batch."
                )

            if (
                request.status
                == ChemicalAnalysisRequest.Status.COMPLETED
            ):
                errors["chemical_analysis_request"] = (
                    "A checklist cannot be completed after the "
                    "analysis request has already been completed."
                )

        batch = batch or self._get_batch(request)

        if batch is None:
            errors["chemical_analysis_request"] = (
                "The analysis request must have an associated "
                "chemical batch."
            )

        if not self.chemical_id:
            errors["chemical"] = (
                "A chemical is required before completing "
                "the checklist."
            )

        if batch is not None:
            if (
                batch.chemical_id
                and self.chemical_id
                and batch.chemical_id != self.chemical_id
            ):
                errors["chemical"] = (
                    "The checklist chemical must match "
                    "the batch chemical."
                )

        if (
            self.manufacture_date
            and self.expiry_date
            and self.expiry_date < self.manufacture_date
        ):
            errors["expiry_date"] = (
                "The expiry date cannot be earlier than "
                "the manufacture date."
            )

        if (
            self.expiry_date
            and self.expiry_date < timezone.localdate()
        ):
            errors["expiry_date"] = (
                "The chemical batch has expired."
            )

        if (
            self.net_weight is None
            or self.net_weight <= Decimal("0")
        ):
            errors["net_weight"] = (
                "Net weight must be greater than zero."
            )

        if (
            not isinstance(self.storage_conditions, str)
            or not self.storage_conditions.strip()
        ):
            errors["storage_conditions"] = (
                "Storage conditions are required."
            )

        if self.sampled_by_id is None:
            errors["sampled_by"] = (
                "A user who sampled the chemical is required."
            )

        if self.requested_by_id is None:
            errors["requested_by"] = (
                "The user who requested the analysis is required."
            )

        if errors:
            raise ValidationError(errors)

    def mark_completed(self, performed_by=None):
        if self.completed:
            raise ValidationError(
                "Checklist is already marked as completed."
            )

        if performed_by is None:
            raise ValidationError(
                "A user is required to complete the checklist."
            )

        if not getattr(
            performed_by,
            "is_authenticated",
            False,
        ):
            raise ValidationError(
                "The completing user must be authenticated."
            )

        if not getattr(
            performed_by,
            "is_active",
            False,
        ):
            raise ValidationError(
                "An inactive user cannot complete a checklist."
            )

        with transaction.atomic():
            checklist = (
                type(self).objects
                .select_for_update()
                .select_related(
                    "chemical_analysis_request",
                    "chemical_analysis_request__batch",
                    "chemical_analysis_request__location",
                    "chemical",
                )
                .get(pk=self.pk)
            )

            if checklist.completed:
                raise ValidationError(
                    "Checklist is already marked as completed."
                )

            request = checklist.chemical_analysis_request
            batch = checklist._get_batch(request)

            checklist.validate_completion_requirements(
                request=request,
                batch=batch,
            )

            now = timezone.now()

            checklist.completed = True
            checklist.completed_at = now
            checklist.completed_by = performed_by

            checklist.full_clean()

            type(self).objects.filter(
                pk=checklist.pk,
            ).update(
                completed=True,
                completed_at=now,
                completed_by_id=performed_by.pk,
                updated_at=now,
            )

            checklist_id = checklist.pk

            transaction.on_commit(
                lambda checklist_id=checklist_id: (
                    checklist_completed.send(
                        sender=type(self),
                        instance=type(self).objects.get(
                            pk=checklist_id,
                        ),
                        old_status="PENDING",
                        new_status="COMPLETED",
                        performed_by=performed_by,
                    )
                )
            )

        self.completed = True
        self.completed_at = now
        self.completed_by_id = performed_by.pk

        return self

    def reopen(self, performed_by=None):
        if not self.completed:
            raise ValidationError(
                "Checklist is not completed."
            )

        if performed_by is None:
            raise ValidationError(
                "A user is required to reopen the checklist."
            )

        if not getattr(
            performed_by,
            "is_authenticated",
            False,
        ):
            raise ValidationError(
                "The reopening user must be authenticated."
            )

        if not getattr(
            performed_by,
            "is_active",
            False,
        ):
            raise ValidationError(
                "An inactive user cannot reopen a checklist."
            )

        with transaction.atomic():
            checklist = (
                type(self).objects
                .select_for_update()
                .get(pk=self.pk)
            )

            if not checklist.completed:
                raise ValidationError(
                    "Checklist is already open."
                )

            now = timezone.now()

            type(self).objects.filter(
                pk=checklist.pk,
            ).update(
                completed=False,
                completed_at=None,
                completed_by_id=None,
                updated_at=now,
            )

        self.completed = False
        self.completed_at = None
        self.completed_by_id = None

        return self

    def save(self, *args, **kwargs):
        if self.completed:
            if not self.completed_at:
                self.completed_at = timezone.now()

            if not self.completed_by_id:
                raise ValidationError(
                    "A completed checklist must have "
                    "a completing user."
                )
        else:
            self.completed_at = None
            self.completed_by_id = None

        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    def __str__(self):
        chemical_name = (
            self.chemical.name
            if self.chemical_id
            else "Unknown Chemical"
        )

        batch_number = self.batch_number or "N/A"

        return (
            f"Checklist - {chemical_name} "
            f"({batch_number})"
        )

class ChemicalAnalysisProcess(Process):
    class WorkflowStatus(models.TextChoices):
        CREATED = "CREATED", "Created"
        RECEIVED = "RECEIVED", "Received"
        REQUESTED = "REQUESTED", "Requested"
        ASSIGNED = "ASSIGNED", "Assigned"
        CHECKLIST = "CHECKLIST", "Checklist"
        ANALYSIS = "ANALYSIS", "Analysis"
        RETEST = "RETEST", "Retest"
        QA = "QA", "Quality Assurance"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        UTILIZED = "UTILIZED", "Utilized"
        RETURNED = "RETURNED", "Returned"
        COMPLETED = "COMPLETED", "Completed"

    batch = models.OneToOneField(
        "ChemicalBatch",
        on_delete=models.CASCADE,
        related_name="analysis_process",
    )

    analysis_request = models.OneToOneField(
        "ChemicalAnalysisRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analysis_process",
    )

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_chemical_analysis_processes",
    )

    assigned_analyst = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performed_chemical_analysis_processes",
    )

    qa_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="qa_chemical_analysis_processes",
    )

    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_chemical_analysis_processes",
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    checklist_completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    analysis_started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    analysis_completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    qa_reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    rejected_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    rework_count = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("receive_chemical_batch", "Can receive chemical batches"),
            ("create_analysis_request", "Can create chemical analysis requests"),
            ("complete_receiving_checklist", "Can complete receiving checklists"),
            ("start_chemical_analysis", "Can start chemical analysis"),
            ("record_chemical_result", "Can record chemical test results"),
            ("complete_chemical_analysis", "Can complete chemical analysis"),
            ("perform_chemical_retest", "Can perform chemical retests"),
            ("review_chemical_analysis", "Can review chemical analysis"),
            ("verify_chemical_coa", "Can verify chemical CoA"),
            ("approve_chemical_coa", "Can generate and approve chemical CoA"),
            ("approve_chemical_batch", "Can approve chemical batches"),
            ("reject_chemical_batch", "Can reject chemical batches"),
            ("utilize_chemical_batch", "Can utilize chemical batches"),
            ("return_chemical_batch", "Can return chemical batches"),
            ("reopen_chemical_checklist", "Can reopen chemical checklists"),
        ]
        indexes = [

            models.Index(
                fields=["assigned_analyst", "analysis_started_at"],
                name="ca_proc_analyst_start_idx",
            ),
            models.Index(
                fields=["qa_officer", "qa_reviewed_at"],
                name="ca_proc_qa_review_idx",
            ),
            models.Index(
                fields=["approver", "approved_at"],
                name="ca_proc_approver_idx",
            ),
            models.Index(
                fields=["analysis_started_at", "analysis_completed_at"],
                name="ca_proc_analysis_period_idx",
            ),
            models.Index(
                fields=["completed_at"],
                name="ca_proc_completed_idx",
            ),
        ]

    @property
    def chemical(self):
        return self.batch.chemical if self.batch_id else None

    @property
    def supplier(self):
        return self.batch.supplier if self.batch_id else None

    @property
    def treatment_plant(self):
        return self.batch.treatment_plant if self.batch_id else None

    @property
    def sample_id(self):
        return self.batch.sample_id if self.batch_id else None

    @property
    def batch_number(self):
        return self.batch.batch_number if self.batch_id else None

    @property
    def test_results(self):
        if not self.batch_id:
            return BatchTestResult.objects.none()

        return self.batch.test_results.all()

    def required_specifications(self):
        if not self.batch_id or not self.batch.chemical_id:
            return ChemicalSpecification.objects.none()

        return (
            ChemicalSpecification.objects
            .filter(
                chemical_id=self.batch.chemical_id,
                treatment_plant_id=self.batch.treatment_plant_id,
                is_required=True,
            )
            .select_related(
                "chemical",
                "method",
            )
            .prefetch_related("remarks")
            .order_by(
                "parameter_name",
                "version",
            )
        )

    @property
    def pending_tests(self):
        if not self.batch_id:
            return BatchTestResult.objects.none()

        return (
            self.batch.test_results
            .filter(
                Q(status__isnull=True) | Q(status="")
            )
            .select_related(
                "parameter",
                "parameter__chemical",
            )
            .order_by(
                "parameter__parameter_name",
                "id",
            )
        )

    @property
    def completed_tests(self):
        if not self.batch_id:
            return BatchTestResult.objects.none()

        return (
            self.batch.test_results
            .exclude(
                Q(status__isnull=True) | Q(status="")
            )
            .select_related(
                "parameter",
                "parameter__chemical",
            )
            .order_by(
                "parameter__parameter_name",
                "id",
            )
        )

    @property
    def failed_tests(self):
        if not self.batch_id:
            return BatchTestResult.objects.none()

        return (
            self.batch.test_results
            .filter(
                status=BatchTestResult.Status.FAIL
            )
            .select_related(
                "parameter",
                "parameter__chemical",
            )
            .order_by(
                "parameter__parameter_name",
                "id",
            )
        )

    @property
    def has_pending_tests(self):
        return self.pending_tests.exists()

    @property
    def next_test(self):
        return self.pending_tests.first()

    @property
    def pending_inputs(self):
        if not self.batch_id:
            return ChemicalAnalysisInput.objects.none()

        return (
            ChemicalAnalysisInput.objects
            .filter(
                test_result__batch_id=self.batch_id
            )
            .filter(
                Q(calculated_value__isnull=True)
                | Q(inputs={})
            )
            .select_related(
                "test_result",
                "test_result__parameter",
            )
        )

    @property
    def required_test_count(self):
        return self.required_specifications().count()

    @property
    def completed_test_count(self):
        required_ids = self.required_specifications().values_list(
            "pk",
            flat=True,
        )

        if not required_ids.exists():
            return self.completed_tests.count()

        return (
            self.batch.test_results
            .filter(
                parameter_id__in=required_ids
            )
            .exclude(
                Q(status__isnull=True) | Q(status="")
            )
            .values("parameter_id")
            .distinct()
            .count()
        )

    @property
    def passed_test_count(self):
        if not self.batch_id:
            return 0

        return self.batch.test_results.filter(
            status=BatchTestResult.Status.PASS
        ).count()

    @property
    def analysis_progress(self):
        required = self.required_test_count

        if required == 0:
            return 100

        return round(
            min(
                self.completed_test_count,
                required,
            ) / required * 100,
            2,
        )

    @property
    def is_analysis_complete(self):
        if not self.batch_id:
            return False

        required = self.required_specifications()

        if not required.exists():
            return self.batch.test_results.exists()

        completed_ids = (
            self.batch.test_results
            .exclude(
                Q(status__isnull=True) | Q(status="")
            )
            .values_list(
                "parameter_id",
                flat=True,
            )
        )

        return not required.exclude(
            pk__in=completed_ids
        ).exists()

    @property
    def is_overdue(self):
        return bool(
            self.analysis_request_id
            and self.analysis_request.is_overdue
        )

    @property
    def analysis_ready(self):
        if not self.analysis_request_id:
            return False

        checklist = (
            self.analysis_request.checklists
            .filter(completed=True)
            .order_by("-completed_at", "-pk")
            .first()
        )

        return bool(checklist)

    @property
    def assigned_analysts(self):
        if not self.analysis_request_id:
            return get_user_model().objects.none()

        return self.analysis_request.assigned_analysts.all()

    @property
    def has_assigned_analysts(self):
        return self.assigned_analysts.exists()

    def is_authorized_analyst(self, user):
        return bool(
            user
            and getattr(user, "is_active", False)
            and self.analysis_request_id
            and self.analysis_request.is_assigned_analyst(user)
        )

    def refresh_assigned_analysts(self):
        if not self.analysis_request_id:
            return get_user_model().objects.none()

        return self.analysis_request.assigned_analysts.all()

    def ensure_result_for_parameter(
        self,
        parameter,
        *,
        analyst=None,
    ):
        if not self.batch_id:
            raise ValidationError(
                "An analysis batch is required."
            )

        if parameter is None:
            raise ValidationError(
                "An analysis parameter is required."
            )

        if parameter.chemical_id != self.batch.chemical_id:
            raise ValidationError(
                "The analysis parameter does not belong "
                "to the batch chemical."
            )

        if analyst is not None and not self.is_authorized_analyst(
            analyst
        ):
            raise ValidationError(
                "The analyst recording the result must be "
                "assigned to this analysis."
            )

        result, created = BatchTestResult.objects.get_or_create(
            batch=self.batch,
            parameter=parameter,
            defaults={
                "analyst": analyst,
            },
        )

        if (
            not created
            and analyst is not None
            and result.analyst_id is None
        ):
            result.analyst = analyst
            result.save(
                update_fields=["analyst"]
            )

        return result

    def move_to_analysis(self):
        """Advance directly from completed checklist to analysis.

        There is deliberately no random/systematic sampling stage in the
        chemical-analysis workflow.
        """
        if self.status != self.WorkflowStatus.CHECKLIST:
            raise ValidationError(
                f"Analysis cannot start from status {self.status}."
            )

        if not self.batch_id or not self.analysis_request_id:
            raise ValidationError(
                "A chemical batch and analysis request are required."
            )

        if not self.has_assigned_analysts:
            raise ValidationError(
                "At least one analyst must be assigned before analysis."
            )

        checklist = (
            self.analysis_request.checklists
            .filter(completed=True)
            .order_by("-completed_at", "-pk")
            .first()
        )

        if checklist is None:
            raise ValidationError(
                "A completed receiving checklist is required."
            )

        now = timezone.now()
        self.checklist_completed_at = (
            self.checklist_completed_at
            or checklist.completed_at
            or now
        )
        self.status = self.WorkflowStatus.ANALYSIS

        self.save(
            update_fields=[
                "status",
                "checklist_completed_at",
                "updated_at",
            ]
        )

        return self

    def mark_analysis_started(
        self,
        performed_by=None,
    ):
        if self.status != self.WorkflowStatus.ANALYSIS:
            raise ValidationError(
                "Analysis can only be started from the analysis stage."
            )

        if not self.analysis_ready:
            raise ValidationError(
                "A completed receiving checklist is required before analysis."
            )

        if (
            performed_by is None
            or not self.is_authorized_analyst(performed_by)
        ):
            raise ValidationError(
                "Only an assigned analyst can start this analysis."
            )

        request = self.analysis_request

        if request.status == (
            ChemicalAnalysisRequest.Status.PENDING
        ):
            request.start_analysis(
                performed_by=performed_by
            )

        now = timezone.now()

        self.status = self.WorkflowStatus.ANALYSIS
        self.started_at = self.started_at or now
        self.analysis_started_at = (
            self.analysis_started_at
            or now
        )
        self.assigned_analyst = performed_by

        self.save(
            update_fields=[
                "status",
                "started_at",
                "analysis_started_at",
                "assigned_analyst",
                "updated_at",
            ]
        )

        return self

    def mark_analysis_completed(
        self,
        performed_by=None,
    ):
        if self.status != self.WorkflowStatus.ANALYSIS:
            raise ValidationError(
                "Chemical analysis is not currently in progress."
            )

        if performed_by is not None:
            if not self.is_authorized_analyst(
                performed_by
            ):
                raise ValidationError(
                    "Only an assigned analyst can "
                    "complete the analysis."
                )

            if (
                self.assigned_analyst_id
                and self.assigned_analyst_id
                != performed_by.pk
            ):
                raise ValidationError(
                    "The analysis must be completed by "
                    "the analyst who started it."
                )

        if (
            not self.is_analysis_complete
            or self.has_pending_tests
        ):
            raise ValidationError(
                "All required analytical results "
                "must be finalized."
            )

        now = timezone.now()

        self.analysis_completed_at = now
        self.status = self.WorkflowStatus.QA

        if self.analysis_request_id:
            request = self.analysis_request

            if request.status == (
                ChemicalAnalysisRequest.Status.IN_PROGRESS
            ):
                request.mark_completed(
                    performed_by=performed_by
                )

        self.save(
            update_fields=[
                "status",
                "analysis_completed_at",
                "updated_at",
            ]
        )

        return self

    def mark_approved(self, approved_by):
        if self.status != self.WorkflowStatus.QA:
            raise ValidationError(
                "Chemical analysis must be in QA before approval."
            )

        if approved_by is None:
            raise ValidationError(
                "An approving user is required."
            )

        if not self.analysis_completed_at:
            raise ValidationError(
                "Chemical analysis must be completed before approval."
            )

        if (
            self.has_pending_tests
            or self.failed_tests.exists()
        ):
            raise ValidationError(
                "Pending or failed analytical results prevent approval."
            )

        now = timezone.now()

        self.qa_officer = (
            self.qa_officer
            or approved_by
        )

        self.qa_reviewed_at = (
            self.qa_reviewed_at
            or now
        )

        self.approver = approved_by
        self.approved_at = now
        self.status = self.WorkflowStatus.APPROVED

        self.batch.status = self.batch.Status.APPROVED

        self.batch.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        self.save(
            update_fields=[
                "status",
                "qa_officer",
                "qa_reviewed_at",
                "approver",
                "approved_at",
                "updated_at",
            ]
        )

        return self

    def mark_rejected(self):
        allowed_statuses = {
            self.WorkflowStatus.QA,
            self.WorkflowStatus.RETEST,
            self.WorkflowStatus.RECEIVED,
            self.WorkflowStatus.CHECKLIST,
            self.WorkflowStatus.ANALYSIS,
        }

        if self.status not in allowed_statuses:
            raise ValidationError(
                f"Chemical process cannot be rejected "
                f"from {self.status}."
            )

        self.status = self.WorkflowStatus.REJECTED
        self.rejected_at = timezone.now()

        if self.batch_id:
            self.batch.status = self.batch.Status.REJECTED

            self.batch.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        self.save(
            update_fields=[
                "status",
                "rejected_at",
                "updated_at",
            ]
        )

        return self

    def mark_disposition_completed(
        self,
        disposition,
    ):
        disposition = str(
            disposition or ""
        ).strip().upper()

        valid_dispositions = {
            self.WorkflowStatus.UTILIZED,
            self.WorkflowStatus.RETURNED,
        }

        if disposition not in valid_dispositions:
            raise ValidationError(
                "Invalid batch disposition."
            )

        if self.status != self.WorkflowStatus.APPROVED:
            raise ValidationError(
                "Batch disposition requires an approved "
                "chemical analysis."
            )

        if not self.batch_id:
            raise ValidationError(
                "A chemical batch is required."
            )

        self.status = disposition
        self.batch.status = disposition

        self.batch.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        self.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return self

    def mark_completed(self):
        if self.status not in {
            self.WorkflowStatus.UTILIZED,
            self.WorkflowStatus.RETURNED,
        }:
            raise ValidationError(
                "The process can only be completed "
                "after batch disposition."
            )

        self.status = self.WorkflowStatus.COMPLETED
        self.completed_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "completed_at",
                "updated_at",
            ]
        )

        return self

    def clean(self):
        super().clean()

        errors = {}

        if not self.batch_id:
            errors["batch"] = (
                "A chemical batch is required."
            )

        if (
            self.analysis_request_id
            and self.batch_id
            and self.analysis_request.batch_id
            != self.batch_id
        ):
            errors["analysis_request"] = (
                "The analysis request must belong "
                "to this chemical batch."
            )

        if (
            self.assigned_analyst_id
            and self.analysis_request_id
            and not self.analysis_request.assigned_analysts.filter(
                pk=self.assigned_analyst_id
            ).exists()
        ):
            errors["assigned_analyst"] = (
                "The assigned analyst must belong "
                "to the analysis request."
            )

        if (
            self.status == self.WorkflowStatus.ANALYSIS
            and not self.analysis_started_at
        ):
            errors["analysis_started_at"] = (
                "Analysis start time is required."
            )

        if (
            self.status in {
                self.WorkflowStatus.RETEST,
                self.WorkflowStatus.QA,
            }
            and not self.analysis_completed_at
        ):
            errors["analysis_completed_at"] = (
                "Original analysis must be completed first."
            )

        if self.status == self.WorkflowStatus.APPROVED:
            if not self.approver_id:
                errors["approver"] = (
                    "An approver is required."
                )

            if not self.approved_at:
                errors["approved_at"] = (
                    "Approval time is required."
                )

        if self.status == self.WorkflowStatus.REJECTED:
            if not self.rejected_at:
                errors["rejected_at"] = (
                    "Rejection time is required."
                )

        if self.status == self.WorkflowStatus.COMPLETED:
            if not self.completed_at:
                errors["completed_at"] = (
                    "Completion time is required."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        now = timezone.now()

        if (
            self.status == self.WorkflowStatus.ANALYSIS
            and not self.analysis_started_at
        ):
            self.analysis_started_at = now

        if (
            self.status == self.WorkflowStatus.APPROVED
            and not self.approved_at
        ):
            self.approved_at = now

        if (
            self.status == self.WorkflowStatus.REJECTED
            and not self.rejected_at
        ):
            self.rejected_at = now

        if (
            self.status == self.WorkflowStatus.COMPLETED
            and not self.completed_at
        ):
            self.completed_at = now

        self.clean()

        return super().save(
            *args,
            **kwargs,
        )

    def __str__(self):
        return (
            f"Chemical Analysis Process - "
            f"{self.sample_id or self.batch_id or 'N/A'} "
            f"[{self.status}]"
        )


class BatchTestResult(models.Model):
    class Status(models.TextChoices):
        PASS = 'PASS', 'Pass'
        FAIL = 'FAIL', 'Fail'
        NA = 'NA', 'Not Applicable'

    batch = models.ForeignKey(ChemicalBatch, on_delete=models.CASCADE, related_name='test_results')
    parameter = models.ForeignKey(ChemicalSpecification, on_delete=models.SET_NULL, null=True)
    value = models.FloatField(null=True, blank=True)
    textual_result = models.CharField(max_length=100, blank=True)

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        null=True,
        blank=True,
        db_index=True,
    )
    tested_at = models.DateTimeField(default=timezone.now)
    analyst = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name="performed_tests",limit_choices_to={ "groups__name__in": ["Laboratory Assistant","Laboratory Technician",] },)
    auto_remark = models.TextField(blank=True)

    class Meta:
        ordering = ["parameter__parameter_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "parameter"],
                name="ca_unique_batch_parameter_result",
            ),
        ]
        indexes = [
            models.Index(fields=["batch", "status"], name="ca_result_batch_status_idx"),
            models.Index(fields=["analyst", "tested_at"], name="ca_result_analyst_tested_idx"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if not self.batch_id:
            errors["batch"] = "A chemical batch is required."
        if not self.parameter_id:
            errors["parameter"] = "An analytical parameter is required."
        if self.parameter_id and self.batch_id:
            parameter = self.parameter
            if parameter.chemical_id != self.batch.chemical_id:
                errors["parameter"] = "The parameter must belong to the batch chemical."
            if self.value is not None and not math.isfinite(float(self.value)):
                errors["value"] = "The analytical value must be finite."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Optimize to single query: directly use .first()
        if self.parameter_id:
            remark = self.parameter.remarks.first()
            if remark:
                if self.status == self.Status.PASS:
                    self.auto_remark = remark.on_pass
                elif self.status == self.Status.FAIL:
                    self.auto_remark = remark.on_fail
                else:
                    self.auto_remark = "Not applicable."
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Test Result - {self.parameter} ({self.status or 'Pending'})"

class ChemicalAnalysisInput(models.Model):
    test_result = models.OneToOneField(
        "BatchTestResult",
        on_delete=models.CASCADE,
        related_name="inputs",
    )

    inputs = models.JSONField(
        default=dict,
        blank=False,
        help_text=(
            "Input values required by the analysis method, "
            "for example: "
            "{'mass1': 5.0, 'mass2': 5.2, 'mass3': 5.1, 'volume': 10.0}"
        ),
    )

    calculated_value = models.FloatField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-pk"]

    def __str__(self):
        return f"Inputs for TestResult #{self.test_result_id}"

    @property
    def test_parameter(self):
        if not self.test_result_id:
            return None

        return self.test_result.parameter

    @property
    def analysis_method(self):
        parameter = self.test_parameter

        if parameter is None:
            return None

        return parameter.method

    @property
    def required_input_fields(self):
        method = self.analysis_method

        if method is None:
            return []

        fields = method.get_input_fields()

        if fields is None:
            return []

        if isinstance(fields, str):
            fields = [
                field.strip()
                for field in fields.split(",")
                if field.strip()
            ]

        try:
            fields = list(fields)
        except TypeError as exc:
            raise ValidationError(
                "The analysis method returned an invalid "
                "input-field definition."
            ) from exc

        normalized = []

        for field in fields:
            if not isinstance(field, str):
                raise ValidationError(
                    "Analysis method input-field names must be strings."
                )

            field = field.strip()

            if not field:
                continue

            if not field.isidentifier():
                raise ValidationError(
                    f"Invalid analysis input field name: '{field}'."
                )

            if field in {"math", "__builtins__"}:
                raise ValidationError(
                    f"Reserved input field name is not allowed: '{field}'."
                )

            if field not in normalized:
                normalized.append(field)

        return normalized

    @property
    def formula(self):
        method = self.analysis_method

        if method is None:
            return None

        return getattr(method, "formula", None)

    @property
    def rounding_precision(self):
        method = self.analysis_method

        if method is None:
            return None

        precision = getattr(
            method,
            "rounding_precision",
            None,
        )

        if precision is None:
            return None

        try:
            precision = int(precision)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "The analysis method rounding precision "
                "must be an integer."
            ) from exc

        if precision < 0 or precision > 15:
            raise ValidationError(
                "The analysis method rounding precision "
                "must be between 0 and 15."
            )

        return precision

    def clean(self):
        super().clean()

        errors = {}

        if not self.test_result_id:
            errors["test_result"] = (
                "A test result is required."
            )

        if not isinstance(self.inputs, dict):
            errors["inputs"] = (
                "Analysis inputs must be provided as a JSON object."
            )

        if errors:
            raise ValidationError(errors)

        if self.test_result_id:
            try:
                test_result = (
                    BatchTestResult.objects
                    .select_related(
                        "parameter",
                        "parameter__method",
                    )
                    .get(pk=self.test_result_id)
                )
            except BatchTestResult.DoesNotExist as exc:
                errors["test_result"] = (
                    "The selected test result does not exist."
                )
            else:
                if test_result.parameter_id is None:
                    errors["test_result"] = (
                        "The test result must have an associated "
                        "parameter."
                    )

                elif test_result.parameter.method_id is None:
                    errors["test_result"] = (
                        "The selected parameter does not have "
                        "an analysis method."
                    )

        if errors:
            raise ValidationError(errors)

        self._validate_inputs()

    def _validate_inputs(self):
        if not isinstance(self.inputs, dict):
            raise ValidationError(
                {
                    "inputs": (
                        "Analysis inputs must be provided "
                        "as a JSON object."
                    )
                }
            )

        required_fields = self.required_input_fields

        if not required_fields:
            if self.formula:
                raise ValidationError(
                    "The analysis method defines a formula "
                    "but no input fields."
                )

            return

        missing = [
            field
            for field in required_fields
            if field not in self.inputs
        ]

        if missing:
            raise ValidationError(
                {
                    "inputs": (
                        "Missing required analysis input(s): "
                        + ", ".join(missing)
                    )
                }
            )

        invalid = []

        for field in required_fields:
            value = self.inputs.get(field)

            if value is None or (
                isinstance(value, str)
                and not value.strip()
            ):
                invalid.append(
                    f"{field} must contain a numeric value"
                )
                continue

            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                invalid.append(
                    f"{field} must contain a numeric value"
                )
                continue

            if not math.isfinite(numeric_value):
                invalid.append(
                    f"{field} must contain a finite numeric value"
                )

        if invalid:
            raise ValidationError(
                {"inputs": invalid}
            )

    def _build_safe_context(self):
        self._validate_inputs()

        context = {
            "math": math,
        }

        for field in self.required_input_fields:
            try:
                value = float(
                    self.inputs[field]
                )
            except (
                TypeError,
                ValueError,
                KeyError,
            ) as exc:
                raise ValidationError(
                    {
                        "inputs": (
                            f"Invalid numeric value for input "
                            f"'{field}'."
                        )
                    }
                ) from exc

            if not math.isfinite(value):
                raise ValidationError(
                    {
                        "inputs": (
                            f"Input '{field}' must contain "
                            "a finite number."
                        )
                    }
                )

            context[field] = value

        return context

    def _validate_formula(self):
        formula = self.formula

        if formula is None:
            return None

        if not isinstance(formula, str):
            raise ValidationError(
                "The analysis method formula must be a string."
            )

        formula = formula.strip()

        if not formula:
            raise ValidationError(
                "The analysis method formula cannot be empty."
            )

        validate_formula_expression(
            formula,
            allow_math_attr=True,
        )

        tree = ast.parse(
            formula,
            mode="eval",
        )

        allowed_names = set(
            self.required_input_fields
        )
        allowed_names.add("math")

        unknown_names = sorted(
            {
                node.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Name)
                and node.id not in allowed_names
            }
        )

        if unknown_names:
            raise ValidationError(
                "The analysis formula references undefined "
                "input variable(s): "
                + ", ".join(unknown_names)
            )

        return formula

    def calculate(self):
        method = self.analysis_method

        if method is None:
            self.calculated_value = None
            return None

        formula = self._validate_formula()

        if not formula:
            self.calculated_value = None
            return None

        context = self._build_safe_context()

        try:
            result = safe_eval_formula(
                formula,
                context,
            )
        except (
            ArithmeticError,
            TypeError,
            ValueError,
            ZeroDivisionError,
            OverflowError,
        ) as exc:
            raise ValidationError(
                f"Formula evaluation error: {exc}"
            ) from exc
        except Exception as exc:
            raise ValidationError(
                f"Formula evaluation failed: {exc}"
            ) from exc

        if isinstance(result, bool):
            raise ValidationError(
                "The analysis formula must return a numeric value."
            )

        try:
            result = float(result)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "The analysis formula must return a numeric value."
            ) from exc

        if not math.isfinite(result):
            raise ValidationError(
                "The analysis formula produced a non-finite result."
            )

        precision = self.rounding_precision

        if precision is not None:
            result = round(
                result,
                precision,
            )

        if not math.isfinite(result):
            raise ValidationError(
                "The calculated analysis result is not finite."
            )

        self.calculated_value = result

        return result

    def recalculate(self):
        self.calculated_value = self.calculate()
        return self.calculated_value

    def save(self, *args, **kwargs):
        self.full_clean()
        self.calculate()

        super().save(
            *args,
            **kwargs,
        )




class ChemicalCoA(models.Model):
    batch = models.OneToOneField(
        "ChemicalBatch",
        on_delete=models.CASCADE,
        related_name="coa",
    )
    title = models.CharField(
        max_length=255,
        default="Certificate of Analysis",
    )
    coa_header = models.TextField(blank=True)
    coa_footer = models.TextField(blank=True)

    footer_image = models.ImageField(
        upload_to="reports/chemical_coas/footers/",
        null=True,
        blank=True,
    )
    watermark = models.ImageField(
        upload_to="reports/chemical_coas/watermarks/",
        null=True,
        blank=True,
    )
    qr_code = models.ImageField(
        upload_to="reports/chemical_coas/qr_codes/",
        null=True,
        blank=True,
    )
    pdf_file = models.FileField(
        upload_to="reports/chemical_coas/pdfs/",
        null=True,
        blank=True,
    )

    chemical_name = models.CharField(
        max_length=255,
        editable=False,
        blank=True,
    )
    supplier_name = models.CharField(
        max_length=255,
        editable=False,
        blank=True,
    )
    quantity = models.FloatField(
        editable=False,
        null=True,
        blank=True,
    )
    delivered_to = models.CharField(
        max_length=255,
        editable=False,
        blank=True,
    )
    delivery_date = models.DateField(
        editable=False,
        null=True,
        blank=True,
    )
    delivery_note_number = models.CharField(
        max_length=100,
        editable=False,
        blank=True,
    )
    packaging_status = models.ForeignKey(
        "PackagingStatus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chemical_coas",
    )
    sampling_date = models.DateField(
        editable=False,
        null=True,
        blank=True,
    )
    analysis_date = models.DateField(
        editable=False,
        null=True,
        blank=True,
    )

    results_summary = models.TextField(blank=True)
    remarks = models.TextField(blank=True)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_chemical_coas",
    )
    approved_on = models.DateTimeField(
        null=True,
        blank=True,
    )

    date_of_report = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    verified_hash = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
    )

    class Meta:
        ordering = ["-date_of_report"]
        indexes = [
            models.Index(
                fields=["approved_by", "-approved_on"],
                name="ca_coa_approved_idx",
            ),
            models.Index(
                fields=["-date_of_report"],
                name="ca_coa_report_date_idx",
            ),
            models.Index(
                fields=["batch", "approved_on"],
                name="ca_coa_batch_approval_idx",
            ),
        ]

    def __str__(self):
        return (
            f"COA - {self.chemical_name or 'N/A'} "
            f"[{self.sample_id or 'N/A'}]"
        )

    @property
    def analysis_request(self):
        if not self.batch_id:
            return None

        return getattr(
            self.batch,
            "analysis_request",
            None,
        )

    @property
    def sample_id(self):
        if not self.batch_id:
            return None

        return getattr(
            self.batch,
            "sample_id",
            None,
        )

    @property
    def treatment_plant(self):
        if not self.batch_id:
            return None

        return getattr(
            self.batch,
            "treatment_plant",
            None,
        )

    @property
    def chemical(self):
        if not self.batch_id:
            return None

        return getattr(
            self.batch,
            "chemical",
            None,
        )

    @property
    def supplier(self):
        if not self.batch_id:
            return None

        return getattr(
            self.batch,
            "supplier",
            None,
        )

    @property
    def analysis_status(self):
        request = self.analysis_request

        if request is None:
            return None

        return getattr(
            request,
            "status",
            None,
        )

    @property
    def has_failed_results(self):
        return (
            bool(self.batch_id)
            and self.batch.test_results.filter(
                status=BatchTestResult.Status.FAIL
            ).exists()
        )

    @property
    def has_na_results(self):
        return (
            bool(self.batch_id)
            and self.batch.test_results.filter(
                status=BatchTestResult.Status.NA
            ).exists()
        )

    @property
    def has_pending_results(self):
        if not self.batch_id:
            return False

        return self.batch.test_results.filter(
            Q(status__isnull=True)
            | Q(status="")
        ).exists()

    @property
    def is_approved(self):
        return bool(
            self.approved_by_id
            and self.approved_on
        )

    @property
    def is_locked(self):
        return self.is_approved

    @property
    def is_complete(self):
        return not self.missing_assets

    @property
    def missing_assets(self):
        missing = []

        if not self.qr_code or not self.qr_code.name:
            missing.append("QR Code")

        if not self.pdf_file or not self.pdf_file.name:
            missing.append("PDF File")

        return missing

    @property
    def result_counts(self):
        return self.get_result_counts()

    @property
    def integrity_status(self):
        if not self.is_approved:
            return "UNAPPROVED"

        if not self.verified_hash:
            return "UNVERIFIED"

        return "VALID" if self.verify_integrity() else "INVALID"

    @property
    def generation_status(self):
        if not self.batch_id:
            return "NO_BATCH"

        if not self.can_generate():
            return "NOT_READY"

        if not self.watermark:
            return "PENDING_WATERMARK"

        if not self.qr_code:
            return "PENDING_QR"

        if not self.pdf_file:
            return "PENDING_PDF"

        if self.is_approved:
            return "APPROVED"

        return "READY"

    def clean(self):
        super().clean()

        errors = {}

        if not self.batch_id:
            errors["batch"] = (
                "A chemical batch is required for a CoA."
            )
        else:
            batch = self.batch

            if batch is None:
                errors["batch"] = (
                    "The selected chemical batch does not exist."
                )
            else:
                request = getattr(
                    batch,
                    "analysis_request",
                    None,
                )

                if request is None:
                    errors["batch"] = (
                        "The chemical batch must have an associated "
                        "chemical analysis request."
                    )

                if batch.quantity_received is not None:
                    try:
                        quantity_received = float(
                            batch.quantity_received
                        )
                    except (TypeError, ValueError):
                        errors["batch"] = (
                            "The chemical batch quantity must be numeric."
                        )
                    else:
                        if not math.isfinite(quantity_received):
                            errors["batch"] = (
                                "The chemical batch quantity must be finite."
                            )
                        elif quantity_received <= 0:
                            errors["batch"] = (
                                "The chemical batch quantity must be "
                                "greater than zero."
                            )

                if request is not None:
                    if (
                        request.batch_id
                        and request.batch_id != batch.pk
                    ):
                        errors["batch"] = (
                            "The CoA batch and analysis request "
                            "are inconsistent."
                        )

        if self.quantity is not None:
            try:
                quantity = float(self.quantity)
            except (TypeError, ValueError):
                errors["quantity"] = (
                    "CoA quantity must be numeric."
                )
            else:
                if not math.isfinite(quantity):
                    errors["quantity"] = (
                        "CoA quantity must be finite."
                    )
                elif quantity <= 0:
                    errors["quantity"] = (
                        "CoA quantity must be greater than zero."
                    )

        if self.delivery_date and self.sampling_date:
            if self.sampling_date < self.delivery_date:
                errors["sampling_date"] = (
                    "Sampling date cannot be earlier "
                    "than the delivery date."
                )

        if self.sampling_date and self.analysis_date:
            if self.analysis_date < self.sampling_date:
                errors["analysis_date"] = (
                    "Analysis date cannot be earlier "
                    "than the sampling date."
                )

        if self.approved_on and not self.approved_by_id:
            errors["approved_by"] = (
                "An approving user is required when an "
                "approval timestamp is present."
            )

        if self.approved_by_id and not self.approved_on:
            errors["approved_on"] = (
                "An approval timestamp is required when an "
                "approving user is present."
            )

        if self.is_approved and not self.verified_hash:
            errors["verified_hash"] = (
                "An approved CoA must have a verification hash."
            )

        if errors:
            raise ValidationError(errors)

    def _get_results_queryset(self):
        if not self.batch_id:
            return BatchTestResult.objects.none()

        return (
            self.batch.test_results
            .select_related(
                "parameter",
                "parameter__chemical",
                "parameter__method",
                "analyst",
            )
            .order_by(
                "parameter__chemical__name",
                "parameter__parameter_name",
                "id",
            )
        )

    def get_results(self):
        return self._get_results_queryset()

    def get_result_counts(self):
        queryset = self._get_results_queryset()

        return {
            "total": queryset.count(),
            "pass": queryset.filter(
                status=BatchTestResult.Status.PASS
            ).count(),
            "fail": queryset.filter(
                status=BatchTestResult.Status.FAIL
            ).count(),
            "na": queryset.filter(
                status=BatchTestResult.Status.NA
            ).count(),
            "pending": queryset.filter(
                Q(status__isnull=True)
                | Q(status="")
            ).count(),
        }

    def _serialize_results_digest(self):
        results = []

        for result in self._get_results_queryset():
            parameter = result.parameter

            chemical_name = ""
            parameter_name = "Unspecified Parameter"

            if parameter is not None:
                parameter_name = (
                    parameter.parameter_name
                    or "Unnamed Parameter"
                )

                if parameter.chemical_id:
                    chemical = parameter.chemical
                    chemical_name = (
                        getattr(
                            chemical,
                            "name",
                            "",
                        )
                        or ""
                    )

            results.append(
                {
                    "id": result.pk,
                    "parameter_id": result.parameter_id or "",
                    "parameter": parameter_name,
                    "chemical": chemical_name,
                    "value": (
                        float(result.value)
                        if result.value is not None
                        else None
                    ),
                    "textual_result": (
                        result.textual_result or ""
                    ),
                    "status": result.status or "",
                    "tested_at": (
                        result.tested_at.isoformat()
                        if result.tested_at
                        else None
                    ),
                    "analyst_id": result.analyst_id or "",
                }
            )

        return json.dumps(
            results,
            separators=(",", ":"),
            ensure_ascii=False,
            sort_keys=True,
        )

    def generate_hash(self):
        content = {
            "version": 3,
            "batch_id": self.batch_id or "",
            "sample_id": self.sample_id or "",
            "title": self.title or "",
            "chemical_name": self.chemical_name or "",
            "supplier_name": self.supplier_name or "",
            "quantity": (
                float(self.quantity)
                if self.quantity is not None
                else None
            ),
            "delivered_to": self.delivered_to or "",
            "delivery_date": (
                self.delivery_date.isoformat()
                if self.delivery_date
                else ""
            ),
            "delivery_note_number": (
                self.delivery_note_number or ""
            ),
            "sampling_date": (
                self.sampling_date.isoformat()
                if self.sampling_date
                else ""
            ),
            "analysis_date": (
                self.analysis_date.isoformat()
                if self.analysis_date
                else ""
            ),
            "packaging_status_id": (
                self.packaging_status_id or ""
            ),
            "approved_by": (
                self.approved_by_id or ""
            ),
            "approved_on": (
                self.approved_on.isoformat()
                if self.approved_on
                else ""
            ),
            "results_digest": (
                self._serialize_results_digest()
            ),
            "results_summary": (
                self.results_summary or ""
            ),
            "remarks": (
                self.remarks or ""
            ),
        }

        payload = json.dumps(
            content,
            separators=(",", ":"),
            ensure_ascii=False,
            sort_keys=True,
        )

        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    def generate_remarks(self):
        queryset = self._get_results_queryset()

        if not queryset.exists():
            return "No test results available."

        pending = queryset.filter(
            Q(status__isnull=True)
            | Q(status="")
        ).exists()

        if pending:
            return (
                "Analytical testing is incomplete. "
                "All test results must be finalized before "
                "the CoA can be approved."
            )

        failed = queryset.filter(
            status=BatchTestResult.Status.FAIL
        ).exists()

        if failed:
            return (
                "Batch failed one or more quality specifications. "
                "Not suitable for use."
            )

        applicable_count = queryset.exclude(
            status=BatchTestResult.Status.NA
        ).count()

        na_count = queryset.filter(
            status=BatchTestResult.Status.NA
        ).count()

        if applicable_count == 0:
            return (
                "No applicable quality parameters were identified."
            )

        if na_count:
            return (
                "Batch passed all applicable quality specifications. "
                "Some parameters were not applicable."
            )

        return (
            "Batch passed all quality specifications. "
            "Approved for use."
        )

    def generate_results_summary(self):
        queryset = self._get_results_queryset()

        if not queryset.exists():
            return "No test results available."

        lines = []

        for result in queryset:
            parameter = result.parameter

            if parameter is None:
                label = "Unspecified Parameter"
            else:
                chemical_name = ""

                if parameter.chemical_id:
                    chemical_name = (
                        getattr(
                            parameter.chemical,
                            "name",
                            "",
                        )
                        or ""
                    )

                parameter_name = (
                    parameter.parameter_name
                    or "Unnamed Parameter"
                )

                label = (
                    f"{chemical_name} - {parameter_name}"
                    if chemical_name
                    else parameter_name
                )

            if result.value is not None:
                value = str(result.value)
            elif result.textual_result:
                value = result.textual_result
            else:
                value = "N/A"

            status = (
                result.get_status_display()
                if result.status
                else "Pending"
            )

            lines.append(
                f"{label}: {value} ({status})"
            )

        return "\n".join(lines)

    def auto_populate(self, force=False):
        if not self.batch_id:
            raise ValidationError(
                "Cannot populate CoA without an associated "
                "chemical batch."
            )

        batch = (
            ChemicalBatch.objects
            .select_related(
                "chemical",
                "supplier",
                "treatment_plant",
            )
            .get(pk=self.batch_id)
        )

        request = getattr(
            batch,
            "analysis_request",
            None,
        )

        if request is None:
            raise ValidationError(
                "Cannot populate CoA without an associated "
                "chemical analysis request."
            )

        request = (
            ChemicalAnalysisRequest.objects
            .select_related(
                "location",
                "batch",
            )
            .get(pk=request.pk)
        )

        chemical = batch.chemical
        supplier = batch.supplier
        treatment_plant = batch.treatment_plant

        if force or not self.chemical_name:
            self.chemical_name = (
                getattr(
                    chemical,
                    "name",
                    "",
                )
                or ""
            )

        if force or not self.supplier_name:
            self.supplier_name = (
                getattr(
                    supplier,
                    "name",
                    "",
                )
                or ""
            )

        if force or self.quantity is None:
            self.quantity = batch.quantity_received

        location = getattr(
            request,
            "location",
            None,
        )

        if force or not self.delivered_to:
            self.delivered_to = (
                getattr(
                    location,
                    "name",
                    "",
                )
                or getattr(
                    treatment_plant,
                    "name",
                    "",
                )
                or ""
            )

        if force or not self.delivery_date:
            self.delivery_date = (
                getattr(
                    request,
                    "delivery_date",
                    None,
                )
                or getattr(
                    batch,
                    "received_date",
                    None,
                )
                or timezone.now().date()
            )

        if force or not self.delivery_note_number:
            self.delivery_note_number = (
                getattr(
                    batch,
                    "delivery_note_number",
                    "",
                )
                or ""
            )

        if force or not self.sampling_date:
            if getattr(
                request,
                "analysis_started_at",
                None,
            ):
                self.sampling_date = (
                    request.analysis_started_at.date()
                )
            else:
                self.sampling_date = (
                    getattr(
                        batch,
                        "received_date",
                        None,
                    )
                    or timezone.now().date()
                )

        latest_checklist = None

        if hasattr(request, "checklists"):
            latest_checklist = (
                request.checklists
                .order_by("-created_at")
                .first()
            )

        if force or not self.analysis_date:
            if latest_checklist:
                self.analysis_date = (
                    latest_checklist.created_at.date()
                )
            elif getattr(
                request,
                "completed_at",
                None,
            ):
                self.analysis_date = (
                    request.completed_at.date()
                )
            elif getattr(
                request,
                "analysis_started_at",
                None,
            ):
                self.analysis_date = (
                    request.analysis_started_at.date()
                )
            else:
                self.analysis_date = self.sampling_date

        plant_name = (
            getattr(
                treatment_plant,
                "name",
                "",
            )
            or ""
        )

        plant_address = (
            getattr(
                treatment_plant,
                "address",
                "",
            )
            or ""
        )

        if force or not self.coa_header:
            self.coa_header = " - ".join(
                value
                for value in (
                    plant_name,
                    plant_address,
                )
                if value
            )

        chemical_grade = (
            getattr(
                chemical,
                "grade",
                "",
            )
            or "N/A"
        )

        if force or not self.coa_footer:
            self.coa_footer = (
                f"Chemical Grade: {chemical_grade}"
            )

        return self

    def validate_generation_requirements(self):
        if not self.batch_id:
            raise ValidationError(
                "Cannot generate CoA without an associated "
                "chemical batch."
            )

        batch = self.batch

        if batch is None:
            raise ValidationError(
                "The associated chemical batch does not exist."
            )

        request = self.analysis_request

        if request is None:
            raise ValidationError(
                "Cannot generate CoA without an associated "
                "chemical analysis request."
            )

        if request.status != (
            ChemicalAnalysisRequest.Status.COMPLETED
        ):
            raise ValidationError(
                "Cannot generate CoA before the chemical analysis "
                "request is completed."
            )

        if batch.status not in (
            ChemicalBatch.Status.ANALYSED,
            ChemicalBatch.Status.APPROVED,
            ChemicalBatch.Status.UTILIZED,
            ChemicalBatch.Status.RETURNED,
        ):
            raise ValidationError(
                "The chemical batch must complete analysis before "
                "a CoA can be generated."
            )

        results = self._get_results_queryset()

        if not results.exists():
            raise ValidationError(
                "Cannot generate CoA without analytical test results."
            )

        if results.filter(
            Q(status__isnull=True)
            | Q(status="")
        ).exists():
            raise ValidationError(
                "All analytical test results must have a status "
                "before a CoA can be generated."
            )

        required_specifications = (
            ChemicalSpecification.objects
            .filter(
                chemical_id=batch.chemical_id,
                treatment_plant_id=batch.treatment_plant_id,
                is_required=True,
            )
            .order_by(
                "parameter_name",
                "version",
            )
        )

        if required_specifications.exists():
            completed_parameter_ids = set(
                results.exclude(
                    status=BatchTestResult.Status.NA
                )
                .exclude(
                    parameter_id__isnull=True
                )
                .values_list(
                    "parameter_id",
                    flat=True,
                )
            )

            missing = (
                required_specifications
                .exclude(
                    pk__in=completed_parameter_ids
                )
            )

            if missing.exists():
                names = list(
                    missing.values_list(
                        "parameter_name",
                        flat=True,
                    )[:20]
                )

                raise ValidationError(
                    "Cannot generate CoA because required analytical "
                    "parameters are missing: "
                    + ", ".join(
                        name
                        for name in names
                        if name
                    )
                )

        if self.has_failed_results:
            raise ValidationError(
                "Cannot generate an approval-ready CoA because "
                "one or more analytical results failed."
            )

    def can_generate(self):
        try:
            self.validate_generation_requirements()
        except ValidationError:
            return False

        return True

    def approve(self, approved_by):
        if approved_by is None:
            raise ValidationError(
                "An approving user is required."
            )

        if not getattr(
            approved_by,
            "is_active",
            True,
        ):
            raise ValidationError(
                "An inactive user cannot approve a CoA."
            )

        if self.is_approved:
            raise ValidationError(
                "This CoA has already been approved."
            )

        self.validate_generation_requirements()

        batch = self.batch

        if batch.status != ChemicalBatch.Status.APPROVED:
            raise ValidationError(
                "The chemical batch must be approved before "
                "the CoA can be approved."
            )

        self.auto_populate()

        self.results_summary = (
            self.generate_results_summary()
        )

        self.remarks = (
            self.generate_remarks()
        )

        self.approved_by = approved_by
        self.approved_on = timezone.now()

        self.verified_hash = self.generate_hash()

        self.full_clean()

        self.save(
            populate=False,
            regenerate_watermark=False,
            regenerate_hash=False,
            update_fields=[
                "chemical_name",
                "supplier_name",
                "quantity",
                "delivered_to",
                "delivery_date",
                "delivery_note_number",
                "sampling_date",
                "analysis_date",
                "coa_header",
                "coa_footer",
                "results_summary",
                "remarks",
                "approved_by",
                "approved_on",
                "verified_hash",
                "updated_at",
            ],
        )

        return self

    def revoke_approval(self):
        if not self.is_approved:
            raise ValidationError(
                "This CoA is not currently approved."
            )

        self.approved_by = None
        self.approved_on = None
        self.verified_hash = ""

        self.save(
            populate=False,
            regenerate_watermark=False,
            regenerate_hash=False,
            update_fields=[
                "approved_by",
                "approved_on",
                "verified_hash",
                "updated_at",
            ],
        )

        return self

    def regenerate_content(self):
        if self.is_approved:
            raise ValidationError(
                "Approved CoA content is immutable. "
                "Revoke approval before regenerating content."
            )

        self.validate_generation_requirements()

        self.auto_populate(force=True)

        self.results_summary = (
            self.generate_results_summary()
        )

        self.remarks = (
            self.generate_remarks()
        )

        self.generate_watermark()

        self.verified_hash = ""

        self.full_clean()

        return self

    def verify_integrity(self):
        if not self.verified_hash:
            return False

        if not self.is_approved:
            return False

        try:
            current_hash = self.generate_hash()
        except Exception:
            return False

        return (
            secrets.compare_digest(
                self.verified_hash,
                current_hash,
            )
        )

    def refresh_hash(self):
        if not self.pk:
            raise ValidationError(
                "The CoA must be saved before its hash "
                "can be refreshed."
            )

        if not self.is_approved:
            raise ValidationError(
                "Only an approved CoA can have its "
                "verification hash refreshed."
            )

        new_hash = self.generate_hash()

        type(self).objects.filter(
            pk=self.pk
        ).update(
            verified_hash=new_hash,
            updated_at=timezone.now(),
        )

        self.verified_hash = new_hash

        return new_hash

    def prepare_for_generation(self):
        if self.is_approved:
            raise ValidationError(
                "An approved CoA cannot be regenerated."
            )

        self.validate_generation_requirements()

        self.auto_populate()

        self.results_summary = (
            self.generate_results_summary()
        )

        self.remarks = (
            self.generate_remarks()
        )

        if not self.watermark:
            self.generate_watermark()

        self.verified_hash = ""

        self.full_clean()

        return self

    def ensure_watermark(self):
        if self.watermark and self.watermark.name:
            return self.watermark

        if self.is_approved:
            raise ValidationError(
                "Cannot modify assets of an approved CoA."
            )

        return self.generate_watermark()

    def clear_generated_assets(self):
        if self.is_approved:
            raise ValidationError(
                "Cannot remove generated assets from an approved CoA."
            )

        self.watermark = None
        self.qr_code = None
        self.pdf_file = None
        self.verified_hash = ""

        return self

    def get_result_statistics(self):
        counts = self.get_result_counts()

        total = counts["total"]
        passed = counts["pass"]
        failed = counts["fail"]
        na = counts["na"]
        pending = counts["pending"]

        applicable = max(
            total - na,
            0,
        )

        pass_rate = (
            round(
                (passed / applicable) * 100,
                2,
            )
            if applicable
            else 0.0
        )

        fail_rate = (
            round(
                (failed / applicable) * 100,
                2,
            )
            if applicable
            else 0.0
        )

        completion_rate = (
            round(
                (
                    (total - pending)
                    / total
                ) * 100,
                2,
            )
            if total
            else 0.0
        )

        return {
            "total": total,
            "pass": passed,
            "fail": failed,
            "na": na,
            "pending": pending,
            "applicable": applicable,
            "pass_rate": pass_rate,
            "fail_rate": fail_rate,
            "completion_rate": completion_rate,
        }

    def get_verification_payload(self):
        return {
            "coa_id": self.pk,
            "batch_id": self.batch_id,
            "sample_id": self.sample_id,
            "chemical_name": self.chemical_name,
            "approved": self.is_approved,
            "approved_by_id": self.approved_by_id,
            "approved_on": (
                self.approved_on.isoformat()
                if self.approved_on
                else None
            ),
            "verified_hash": self.verified_hash,
            "integrity": self.integrity_status,
        }

    def save(
        self,
        *args,
        populate=True,
        regenerate_watermark=False,
        regenerate_hash=False,
        generate_assets=False,
        **kwargs,
    ):
        update_fields = kwargs.get(
            "update_fields"
        )

        if self.is_approved:
            protected_fields = {
                "batch",
                "title",
                "coa_header",
                "coa_footer",
                "footer_image",
                "watermark",
                "qr_code",
                "pdf_file",
                "chemical_name",
                "supplier_name",
                "quantity",
                "delivered_to",
                "delivery_date",
                "delivery_note_number",
                "packaging_status",
                "sampling_date",
                "analysis_date",
                "results_summary",
                "remarks",
                "approved_by",
                "approved_on",
                "verified_hash",
            }

            if update_fields is None:
                raise ValidationError(
                    "Approved CoA records require explicit "
                    "update_fields."
                )

            invalid_updates = (
                set(update_fields)
                & protected_fields
            )

            invalid_updates -= {
                "approved_by",
                "approved_on",
                "verified_hash",
            }

            if invalid_updates:
                raise ValidationError(
                    "Approved CoA content is immutable."
                )

        if populate:
            self.auto_populate()

        if not self.remarks:
            self.remarks = (
                self.generate_remarks()
            )

        if not self.results_summary:
            self.results_summary = (
                self.generate_results_summary()
            )

        if (
            generate_assets
            and (
                regenerate_watermark
                or not self.watermark
            )
        ):
            self.generate_watermark()

        if (
            regenerate_hash
            and not self.is_approved
        ):
            self.verified_hash = ""

        if (
            self.is_approved
            and regenerate_hash
        ):
            self.verified_hash = self.generate_hash()

        self.full_clean()

        super().save(
            *args,
            **kwargs,
        )



