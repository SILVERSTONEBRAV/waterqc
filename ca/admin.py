from __future__ import annotations

from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    BatchTestResult,
    Chemical,
    ChemicalAnalysisInput,
    ChemicalAnalysisProcess,
    ChemicalAnalysisRequest,
    ChemicalBatch,
    ChemicalCertApprover,
    ChemicalCoA,
    ChemicalLocation,
    ChemicalSpecification,
    ChemicalSpecificationRemark,
    ChecklistForWaterTreatmentChemicalAnalysis,
    PackagingStatus,
    Supplier,
    SystematicRandomSample,
    SystematicRandomSampling,
)


User = get_user_model()


class PlantScopedAdminMixin:
    plant_lookup = None

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        plant_id = getattr(
            request.user,
            "assigned_treatment_plant_id",
            None,
        )

        if not plant_id:
            return qs.none()

        if not self.plant_lookup:
            return qs

        return qs.filter(
            **{
                self.plant_lookup: plant_id,
            }
        )


class WorkflowAdminMixin:
    workflow_fields = (
        "status",
        "created_at",
        "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(
            super().get_readonly_fields(
                request,
                obj,
            )
        )

        model_fields = {
            field.name
            for field in self.model._meta.fields
        }

        for field in self.workflow_fields:
            if field in model_fields and field not in fields:
                fields.append(field)

        return tuple(fields)

    def _permission_required(
        self,
        request,
        permission: str,
    ):
        if not request.user.has_perm(permission):
            raise PermissionDenied(
                f"Missing required permission: {permission}"
            )

    def _run_action(
        self,
        request,
        queryset,
        permission,
        operation,
        success_message,
        failure_message,
    ):
        self._permission_required(
            request,
            permission,
        )

        success = 0
        failed = 0

        for obj in queryset:
            try:
                with transaction.atomic():
                    operation(obj)
                success += 1
            except (
                ValidationError,
                PermissionDenied,
            ) as exc:
                failed += 1
                self.message_user(
                    request,
                    f"{failure_message} {obj}: {exc}",
                    level=messages.ERROR,
                )
            except Exception as exc:
                failed += 1
                self.message_user(
                    request,
                    f"{failure_message} {obj}: {exc}",
                    level=messages.ERROR,
                )

        if success:
            self.message_user(
                request,
                success_message.format(
                    count=success,
                ),
                level=messages.SUCCESS,
            )

        if failed:
            self.message_user(
                request,
                f"{failed} operation(s) failed.",
                level=messages.WARNING,
            )


class DateRangeFilter(admin.SimpleListFilter):
    title = "age"
    parameter_name = "age"

    def lookups(self, request, model_admin):
        return (
            ("today", "Today"),
            ("7", "Last 7 days"),
            ("30", "Last 30 days"),
            ("90", "Last 90 days"),
            ("older", "Older than 90 days"),
        )

    def queryset(self, request, queryset):
        value = self.value()

        if not value:
            return queryset

        now = timezone.now()

        if value == "today":
            start = now.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            return queryset.filter(
                created_at__gte=start,
            )

        if value in {"7", "30", "90"}:
            start = now - timedelta(
                days=int(value),
            )
            return queryset.filter(
                created_at__gte=start,
            )

        if value == "older":
            return queryset.filter(
                created_at__lt=now - timedelta(days=90),
            )

        return queryset


class OverdueRequestFilter(admin.SimpleListFilter):
    title = "SLA"
    parameter_name = "sla"

    def lookups(self, request, model_admin):
        return (
            ("overdue", "Overdue"),
            ("due_soon", "Due within 2 hours"),
            ("on_track", "On track"),
            ("completed", "Completed"),
        )

    def queryset(self, request, queryset):
        now = timezone.now()

        if self.value() == "overdue":
            return queryset.filter(
                analysis_deadline__lt=now,
            ).exclude(
                status=ChemicalAnalysisRequest.Status.COMPLETED,
            )

        if self.value() == "due_soon":
            return queryset.filter(
                analysis_deadline__gte=now,
                analysis_deadline__lte=now + timedelta(hours=2),
            ).exclude(
                status=ChemicalAnalysisRequest.Status.COMPLETED,
            )

        if self.value() == "on_track":
            return queryset.filter(
                analysis_deadline__gt=now + timedelta(hours=2),
            ).exclude(
                status=ChemicalAnalysisRequest.Status.COMPLETED,
            )

        if self.value() == "completed":
            return queryset.filter(
                status=ChemicalAnalysisRequest.Status.COMPLETED,
            )

        return queryset


class ExpiryFilter(admin.SimpleListFilter):
    title = "expiry"
    parameter_name = "expiry"

    def lookups(self, request, model_admin):
        return (
            ("expired", "Expired"),
            ("today", "Expires today"),
            ("soon", "Within 30 days"),
            ("valid", "Valid"),
        )

    def queryset(self, request, queryset):
        today = timezone.localdate()

        if self.value() == "expired":
            return queryset.filter(
                expiry_date__lt=today,
            )

        if self.value() == "today":
            return queryset.filter(
                expiry_date=today,
            )

        if self.value() == "soon":
            return queryset.filter(
                expiry_date__gt=today,
                expiry_date__lte=today + timedelta(days=30),
            )

        if self.value() == "valid":
            return queryset.filter(
                expiry_date__gt=today + timedelta(days=30),
            )

        return queryset


class SamplingOutcomeFilter(admin.SimpleListFilter):
    title = "sampling outcome"
    parameter_name = "sampling_outcome"

    def lookups(self, request, model_admin):
        return (
            ("pending", "Pending"),
            ("passed", "Passed"),
            ("qa", "QA required"),
            ("approved", "QA approved"),
        )

    def queryset(self, request, queryset):
        value = self.value()

        if value == "pending":
            return queryset.filter(
                status=SystematicRandomSampling.Status.PENDING,
            )

        if value == "passed":
            return queryset.filter(
                sampling_passed=True,
                qa_required=False,
            )

        if value == "qa":
            return queryset.filter(
                qa_required=True,
                qa_approved=False,
            )

        if value == "approved":
            return queryset.filter(
                qa_approved=True,
            )

        return queryset


class IntegrityFilter(admin.SimpleListFilter):
    title = "integrity"
    parameter_name = "integrity"

    def lookups(self, request, model_admin):
        return (
            ("approved", "Approved"),
            ("unverified", "Unverified"),
            ("valid", "Valid"),
            ("invalid", "Invalid"),
            ("unapproved", "Unapproved"),
        )

    def queryset(self, request, queryset):
        value = self.value()

        if value == "approved":
            return queryset.filter(
                approved_by__isnull=False,
                approved_on__isnull=False,
            )

        if value == "unapproved":
            return queryset.filter(
                approved_by__isnull=True,
            )

        if value == "unverified":
            return queryset.filter(
                approved_by__isnull=False,
                verified_hash="",
            )

        if value == "valid":
            return queryset.filter(
                approved_by__isnull=False,
            ).exclude(
                verified_hash="",
            )

        if value == "invalid":
            return queryset.filter(
                approved_by__isnull=False,
                verified_hash="",
            )

        return queryset


class ChemicalSpecificationRemarkInline(admin.TabularInline):
    model = ChemicalSpecificationRemark
    extra = 0
    fields = (
        "on_pass",
        "on_fail",
    )


class ChemicalSpecificationInline(admin.TabularInline):
    model = ChemicalSpecification
    extra = 0
    show_change_link = True
    autocomplete_fields = (
        "method",
        "treatment_plant",
    )
    fields = (
        "parameter_name",
        "unit",
        "method",
        "min_limit",
        "max_limit",
        "is_required",
        "version",
        "treatment_plant",
    )


class BatchTestResultInline(admin.TabularInline):
    model = BatchTestResult
    extra = 0
    show_change_link = True
    autocomplete_fields = (
        "parameter",
        "analyst",
    )
    readonly_fields = (
        "tested_at",
        "auto_remark",
    )
    fields = (
        "parameter",
        "value",
        "textual_result",
        "status",
        "analyst",
        "tested_at",
        "auto_remark",
    )


class SystematicRandomSampleInline(admin.TabularInline):
    model = SystematicRandomSample
    extra = 0
    can_delete = False
    fields = (
        "package_number",
        "declared_net_weight",
        "measured_weight",
        "weight_difference",
    )
    readonly_fields = (
        "package_number",
        "declared_net_weight",
        "weight_difference",
    )


@admin.register(Chemical)
class ChemicalAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "grade",
        "weight_tolerance_display",
        "specification_count",
        "batch_count",
        "formula_status",
    )

    search_fields = (
        "name",
        "code",
        "description",
        "grade",
    )

    list_filter = (
        "grade",
        DateRangeFilter,
    )

    ordering = (
        "name",
        "code",
    )

    list_per_page = 50

    inlines = (
        ChemicalSpecificationInline,
    )

    readonly_fields = (
        "weight_tolerance",
    )

    fieldsets = (
        (
            "Chemical Identity",
            {
                "fields": (
                    "name",
                    "code",
                    "description",
                    "grade",
                )
            },
        ),
        (
            "Analytical Configuration",
            {
                "fields": (
                    "hydrometer_formula",
                    "weight_tolerance",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _specification_count=Count(
                    "specifications",
                    distinct=True,
                ),
                _batch_count=Count(
                    "chemical_batches",
                    distinct=True,
                ),
            )
        )

    @admin.display(
        description="Tolerance",
        ordering="weight_tolerance",
    )
    def weight_tolerance_display(self, obj):
        if obj.weight_tolerance is None:
            return "—"
        return f"{obj.weight_tolerance:g}"

    @admin.display(
        description="Specifications",
        ordering="_specification_count",
    )
    def specification_count(self, obj):
        return obj._specification_count

    @admin.display(
        description="Batches",
        ordering="_batch_count",
    )
    def batch_count(self, obj):
        return obj._batch_count

    @admin.display(description="Formula")
    def formula_status(self, obj):
        if not obj.hydrometer_formula:
            return format_html(
                '<span style="color:#777;">Not configured</span>'
            )

        try:
            obj.clean()
        except ValidationError:
            return format_html(
                '<strong style="color:#b42318;">Invalid</strong>'
            )

        return format_html(
            '<strong style="color:#027a48;">Valid</strong>'
        )


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "contract_number",
        "contract_status",
        "batch_count",
    )

    search_fields = (
        "name",
        "contract_number",
        "contact_info",
    )

    ordering = (
        "name",
    )

    list_per_page = 50

    readonly_fields = (
        "batch_count",
    )

    fieldsets = (
        (
            "Supplier",
            {
                "fields": (
                    "name",
                    "contract_number",
                    "contract_document",
                    "contact_info",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _batch_count=Count(
                    "chemical_batches",
                    distinct=True,
                )
            )
        )

    @admin.display(description="Batches")
    def batch_count(self, obj):
        return obj._batch_count

    @admin.display(description="Contract")
    def contract_status(self, obj):
        if obj.contract_document:
            return format_html(
                '<strong style="color:#027a48;">Attached</strong>'
            )

        return format_html(
            '<strong style="color:#b42318;">Missing</strong>'
        )


@admin.register(ChemicalLocation)
class ChemicalLocationAdmin(
    PlantScopedAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "treatment_plant_id"

    list_display = (
        "name",
        "treatment_plant",
        "request_count",
    )

    search_fields = (
        "name",
        "treatment_plant__name",
    )

    list_filter = (
        "treatment_plant",
    )

    autocomplete_fields = (
        "treatment_plant",
    )

    list_per_page = 50

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "treatment_plant",
            )
            .annotate(
                _request_count=Count(
                    "analysis_requests",
                    distinct=True,
                )
            )
        )

    @admin.display(description="Requests")
    def request_count(self, obj):
        return obj._request_count


@admin.register(ChemicalSpecification)
class ChemicalSpecificationAdmin(
    PlantScopedAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "treatment_plant_id"

    list_display = (
        "chemical",
        "parameter_name",
        "unit",
        "limits_display",
        "required_badge",
        "version",
        "treatment_plant",
        "created_at",
    )

    search_fields = (
        "parameter_name",
        "unit",
        "chemical__name",
        "chemical__code",
        "treatment_plant__name",
    )

    list_filter = (
        "is_required",
        "version",
        "treatment_plant",
        "chemical",
    )

    autocomplete_fields = (
        "chemical",
        "method",
        "treatment_plant",
    )

    readonly_fields = (
        "created_at",
    )

    inlines = (
        ChemicalSpecificationRemarkInline,
    )

    list_per_page = 50

    @admin.display(description="Limits")
    def limits_display(self, obj):
        minimum = (
            "—"
            if obj.min_limit is None
            else str(obj.min_limit)
        )
        maximum = (
            "—"
            if obj.max_limit is None
            else str(obj.max_limit)
        )

        return f"{minimum} → {maximum}"

    @admin.display(description="Required")
    def required_badge(self, obj):
        if obj.is_required:
            return format_html(
                '<strong style="color:#027a48;">YES</strong>'
            )

        return format_html(
            '<span style="color:#777;">NO</span>'
        )


@admin.register(ChemicalSpecificationRemark)
class ChemicalSpecificationRemarkAdmin(
    PlantScopedAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "specification__treatment_plant_id"

    list_display = (
        "specification",
        "chemical",
        "treatment_plant",
    )

    search_fields = (
        "specification__parameter_name",
        "specification__chemical__name",
        "specification__chemical__code",
        "on_pass",
        "on_fail",
    )

    autocomplete_fields = (
        "specification",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "specification",
                "specification__chemical",
                "specification__treatment_plant",
            )
        )

    @admin.display(description="Chemical")
    def chemical(self, obj):
        return obj.specification.chemical

    @admin.display(description="Treatment plant")
    def treatment_plant(self, obj):
        return obj.specification.treatment_plant


@admin.register(PackagingStatus)
class PackagingStatusAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "description",
        "coa_count",
    )

    search_fields = (
        "name",
        "description",
    )

    ordering = (
        "name",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _coa_count=Count(
                    "chemical_coas",
                    distinct=True,
                )
            )
        )

    @admin.display(description="CoAs")
    def coa_count(self, obj):
        return obj._coa_count


@admin.register(ChemicalCertApprover)
class ChemicalCertApproverAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "signature_status",
        "stamp_status",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )

    autocomplete_fields = (
        "user",
    )

    readonly_fields = (
        "user",
    )

    fieldsets = (
        (
            "Approver",
            {
                "fields": (
                    "user",
                    "signature",
                    "rubber_stamp",
                )
            },
        ),
    )

    @admin.display(description="Signature")
    def signature_status(self, obj):
        return (
            "Available"
            if obj.signature
            else "Missing"
        )

    @admin.display(description="Rubber stamp")
    def stamp_status(self, obj):
        return (
            "Available"
            if obj.rubber_stamp
            else "Missing"
        )


@admin.register(ChemicalBatch)
class ChemicalBatchAdmin(
    PlantScopedAdminMixin,
    WorkflowAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "treatment_plant_id"

    list_display = (
        "sample_link",
        "batch_number",
        "chemical",
        "supplier",
        "treatment_plant",
        "quantity_display",
        "status_badge",
        "analysis_state",
        "coa_state",
        "received_date",
    )

    search_fields = (
        "sample_id",
        "batch_number",
        "delivery_note_number",
        "chemical__name",
        "chemical__code",
        "supplier__name",
        "treatment_plant__name",
    )

    list_filter = (
        "status",
        "chemical",
        "supplier",
        "treatment_plant",
        DateRangeFilter,
    )

    autocomplete_fields = (
        "chemical",
        "supplier",
        "treatment_plant",
        "received_by",
    )

    readonly_fields = (
        "sample_id",
        "received_date",
        "created_at",
        "updated_at",
        "coa_generated",
    )

    inlines = (
        BatchTestResultInline,
    )

    actions = (
        "transition_to_approved",
        "transition_to_rejected",
        "transition_to_utilized",
        "transition_to_returned",
    )

    list_select_related = (
        "chemical",
        "supplier",
        "treatment_plant",
        "received_by",
    )

    list_per_page = 50

    fieldsets = (
        (
            "Workflow Identity",
            {
                "fields": (
                    "sample_id",
                    "status",
                    "coa_generated",
                )
            },
        ),
        (
            "Delivery",
            {
                "fields": (
                    "batch_number",
                    "delivery_note_number",
                    "chemical",
                    "supplier",
                    "treatment_plant",
                    "received_date",
                    "received_by",
                    "quantity_received",
                    "unit",
                    "package_count",
                )
            },
        ),
        (
            "Notes",
            {
                "fields": (
                    "remarks",
                )
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Sample ID")
    def sample_link(self, obj):
        url = reverse(
            "admin:ca_chemicalbatch_change",
            args=[obj.pk],
        )

        return format_html(
            '<a href="{}"><strong>{}</strong></a>',
            url,
            obj.sample_id,
        )

    @admin.display(description="Quantity")
    def quantity_display(self, obj):
        return f"{obj.quantity_received:g} {obj.unit}"

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        palette = {
            "RECEIVED": "#175cd3",
            "ANALYSED": "#026aa2",
            "APPROVED": "#027a48",
            "REJECTED": "#b42318",
            "UTILIZED": "#344054",
            "RETURNED": "#93370d",
        }

        color = palette.get(
            obj.status,
            "#475467",
        )

        return format_html(
            '<strong style="color:{};">{}</strong>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Analysis")
    def analysis_state(self, obj):
        process = getattr(
            obj,
            "analysis_process",
            None,
        )

        if process is None:
            return "Not started"

        return process.get_status_display()

    @admin.display(description="CoA")
    def coa_state(self, obj):
        coa = getattr(
            obj,
            "coa",
            None,
        )

        if coa is None:
            return "Not generated"

        if coa.is_approved:
            return "Approved"

        return coa.generation_status

    @admin.action(description="Approve selected batches")
    def transition_to_approved(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.approve_chemical_batch",
            lambda obj: obj.transition_to(
                ChemicalBatch.Status.APPROVED,
                performed_by=request.user,
            ),
            "{} batch(es) approved.",
            "Could not approve",
        )

    @admin.action(description="Reject selected batches")
    def transition_to_rejected(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.reject_chemical_batch",
            lambda obj: obj.transition_to(
                ChemicalBatch.Status.REJECTED,
                performed_by=request.user,
            ),
            "{} batch(es) rejected.",
            "Could not reject",
        )

    @admin.action(description="Utilize selected batches")
    def transition_to_utilized(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.utilize_chemical_batch",
            lambda obj: obj.transition_to(
                ChemicalBatch.Status.UTILIZED,
                performed_by=request.user,
            ),
            "{} batch(es) utilized.",
            "Could not utilize",
        )

    @admin.action(description="Return selected batches")
    def transition_to_returned(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.return_chemical_batch",
            lambda obj: obj.transition_to(
                ChemicalBatch.Status.RETURNED,
                performed_by=request.user,
            ),
            "{} batch(es) returned.",
            "Could not return",
        )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related(
                "test_results",
            )
        )


@admin.register(ChemicalAnalysisRequest)
class ChemicalAnalysisRequestAdmin(
    PlantScopedAdminMixin,
    WorkflowAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "batch__treatment_plant_id"

    list_display = (
        "request_link",
        "sample_id_display",
        "chemical",
        "treatment_plant",
        "status_badge",
        "analyst_count",
        "analyst_assignment_status",
        "sla_status",
        "analysis_started_at",
        "completed_at",
    )

    search_fields = (
        "request_id",
        "batch__sample_id",
        "batch__batch_number",
        "batch__chemical__name",
        "batch__chemical__code",
        "location__name",
        "requested_by__username",
        "assigned_analysts__username",
    )

    list_filter = (
        "status",
        "batch__chemical",
        "batch__supplier",
        "batch__treatment_plant",
        OverdueRequestFilter,
        DateRangeFilter,
    )

    autocomplete_fields = (
        "batch",
        "requested_by",
        "received_by",
        "completed_by",
        "location",
    )

    readonly_fields = (
        "request_id",
        "assigned_analysts_display",
        "analysis_started_at",
        "analysis_deadline",
        "completed_at",
        "created_at",
        "updated_at",
    )

    actions = (
        "start_selected_requests",
        "complete_selected_requests",
        "refresh_selected_analyst_assignments",
    )

    list_select_related = (
        "batch",
        "batch__chemical",
        "batch__supplier",
        "batch__treatment_plant",
        "location",
        "requested_by",
        "received_by",
        "completed_by",
    )

    fieldsets = (
        (
            "Request",
            {
                "fields": (
                    "request_id",
                    "batch",
                    "status",
                )
            },
        ),
        (
            "Receipt",
            {
                "fields": (
                    "requested_by",
                    "received_by",
                    "delivery_date",
                    "location",
                )
            },
        ),
        (
            "Current Analyst Assignment",
            {
                "fields": (
                    "assigned_analysts_display",
                )
            },
        ),
        (
            "SLA",
            {
                "fields": (
                    "analysis_started_at",
                    "analysis_deadline",
                    "completed_at",
                    "completed_by",
                )
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Request ID")
    def request_link(self, obj):
        url = reverse(
            "admin:ca_chemicalanalysisrequest_change",
            args=[obj.pk],
        )

        return format_html(
            '<a href="{}"><strong>{}</strong></a>',
            url,
            obj.request_id,
        )

    @admin.display(description="Sample")
    def sample_id_display(self, obj):
        return obj.sample_id or "—"

    @admin.display(description="Plant")
    def treatment_plant(self, obj):
        return obj.treatment_plant or "—"

    @admin.display(description="Analysts")
    def analyst_count(self, obj):
        return obj.assigned_analyst_count

    @admin.display(description="Assignment")
    def analyst_assignment_status(self, obj):
        count = obj.assigned_analyst_count

        if count:
            return format_html(
                '<strong style="color:#027a48;">{} active analyst(s)</strong>',
                count,
            )

        return format_html(
            '<strong style="color:#b42318;">No current assignment</strong>'
        )

    @admin.display(description="Assigned analysts")
    def assigned_analysts_display(self, obj):
        analysts = list(
            obj.assigned_analysts.filter(
                is_active=True,
            ).order_by(
                "first_name",
                "last_name",
                "username",
            )
        )

        if not analysts:
            return format_html(
                '<strong style="color:#b42318;">'
                "No analysts currently assigned through weekly duty tasks"
                "</strong>"
            )

        return format_html(
            "<br>".join(
                "{} — {}".format(
                    analyst.get_full_name() or analyst.username,
                    analyst.username,
                )
                for analyst in analysts
            )
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "PENDING": "#175cd3",
            "IN_PROGRESS": "#b54708",
            "COMPLETED": "#027a48",
        }

        color = colors.get(
            obj.status,
            "#475467",
        )

        return format_html(
            '<strong style="color:{};">{}</strong>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="SLA")
    def sla_status(self, obj):
        if obj.completed:
            return format_html(
                '<strong style="color:#027a48;">COMPLETED</strong>'
            )

        if obj.is_overdue:
            return format_html(
                '<strong style="color:#b42318;">OVERDUE</strong>'
            )

        remaining = obj.time_remaining

        if remaining is None:
            return "No deadline"

        total_seconds = int(
            remaining.total_seconds()
        )

        hours, remainder = divmod(
            total_seconds,
            3600,
        )
        minutes = remainder // 60

        if hours < 2:
            return format_html(
                '<strong style="color:#b54708;">{}h {}m</strong>',
                hours,
                minutes,
            )

        return f"{hours}h {minutes}m"

    @admin.action(description="Start selected analyses")
    def start_selected_requests(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.start_chemical_analysis",
            lambda obj: obj.start_analysis(
                performed_by=request.user,
            ),
            "{} request(s) started.",
            "Could not start",
        )

    @admin.action(description="Complete selected analyses")
    def complete_selected_requests(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.complete_chemical_analysis",
            lambda obj: obj.mark_completed(
                performed_by=request.user,
            ),
            "{} request(s) completed.",
            "Could not complete",
        )

    @admin.action(
        description="Refresh weekly-task analyst assignments"
    )
    def refresh_selected_analyst_assignments(
        self,
        request,
        queryset,
    ):
        self._permission_required(
            request,
            "ca.start_chemical_analysis",
        )

        success = 0
        failed = 0

        for obj in queryset:
            try:
                with transaction.atomic():
                    obj.populate_assigned_analysts()

                success += 1
            except (
                ValidationError,
                PermissionDenied,
            ) as exc:
                failed += 1
                self.message_user(
                    request,
                    f"{obj}: {exc}",
                    level=messages.ERROR,
                )
            except Exception as exc:
                failed += 1
                self.message_user(
                    request,
                    f"{obj}: {exc}",
                    level=messages.ERROR,
                )

        if success:
            self.message_user(
                request,
                f"{success} request(s) refreshed from weekly duty assignments.",
                level=messages.SUCCESS,
            )

        if failed:
            self.message_user(
                request,
                f"{failed} assignment refresh operation(s) failed.",
                level=messages.WARNING,
            )


@admin.register(SystematicRandomSampling)
class SystematicRandomSamplingAdmin(
    PlantScopedAdminMixin,
    WorkflowAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "batch__treatment_plant_id"

    list_display = (
        "batch_link",
        "sample_count",
        "sampling_interval",
        "random_start",
        "average_weight",
        "weight_difference_display",
        "pass_badge",
        "qa_badge",
        "status_badge",
        "sampled_by",
        "sampled_at",
    )

    search_fields = (
        "batch__sample_id",
        "batch__batch_number",
        "batch__chemical__name",
        "batch__chemical__code",
        "sampled_by__username",
        "counter_checked_by__username",
        "qa_approved_by__username",
    )

    list_filter = (
        "status",
        SamplingOutcomeFilter,
        "qa_required",
        "qa_approved",
        "batch__chemical",
        "batch__treatment_plant",
    )

    autocomplete_fields = (
        "batch",
        "analysis_process",
        "sampled_by",
        "counter_checked_by",
        "qa_approved_by",
    )

    readonly_fields = (
        "sample_count",
        "sampling_interval",
        "random_start",
        "measured_average_weight",
        "average_weight_difference",
        "sampling_passed",
        "qa_required",
        "qa_approved",
        "qa_approved_by",
        "qa_approved_at",
        "sampled_by",
        "sampled_at",
        "counter_checked_by",
        "counter_checked_at",
        "status",
        "created_at",
        "updated_at",
    )

    inlines = (
        SystematicRandomSampleInline,
    )

    actions = (
        "generate_sampling_plans",
        "mark_selected_as_sampled",
        "counter_check_selected",
        "approve_selected_deviations",
    )

    list_select_related = (
        "batch",
        "batch__chemical",
        "batch__treatment_plant",
        "analysis_process",
        "sampled_by",
        "counter_checked_by",
        "qa_approved_by",
    )

    fieldsets = (
        (
            "Sampling Identity",
            {
                "fields": (
                    "batch",
                    "analysis_process",
                    "status",
                )
            },
        ),
        (
            "Sampling Plan",
            {
                "fields": (
                    "sample_count",
                    "sampling_interval",
                    "random_start",
                )
            },
        ),
        (
            "Weight Verification",
            {
                "fields": (
                    "measured_average_weight",
                    "average_weight_difference",
                    "sampling_passed",
                    "qa_required",
                    "qa_approved",
                )
            },
        ),
        (
            "QA",
            {
                "fields": (
                    "qa_approved_by",
                    "qa_approved_at",
                    "verification_notes",
                )
            },
        ),
        (
            "Execution",
            {
                "fields": (
                    "sampled_by",
                    "sampled_at",
                    "counter_checked_by",
                    "counter_checked_at",
                )
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Batch")
    def batch_link(self, obj):
        url = reverse(
            "admin:ca_chemicalbatch_change",
            args=[obj.batch_id],
        )

        return format_html(
            '<a href="{}"><strong>{}</strong></a>',
            url,
            obj.batch,
        )

    @admin.display(description="Average")
    def average_weight(self, obj):
        if obj.measured_average_weight is None:
            return "—"

        return f"{obj.measured_average_weight:g}"

    @admin.display(description="Difference")
    def weight_difference_display(self, obj):
        if obj.average_weight_difference is None:
            return "—"

        return f"{obj.average_weight_difference:g}"

    @admin.display(description="Sampling")
    def pass_badge(self, obj):
        if obj.sampling_passed is True:
            return format_html(
                '<strong style="color:#027a48;">PASS</strong>'
            )

        if obj.sampling_passed is False:
            return format_html(
                '<strong style="color:#b42318;">FAIL</strong>'
            )

        return "Pending"

    @admin.display(description="QA")
    def qa_badge(self, obj):
        if obj.qa_approved:
            return format_html(
                '<strong style="color:#027a48;">APPROVED</strong>'
            )

        if obj.qa_required:
            return format_html(
                '<strong style="color:#b54708;">REQUIRED</strong>'
            )

        return "Not required"

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "PENDING": "#175cd3",
            "SAMPLED": "#026aa2",
            "COUNTER_CHECK": "#b54708",
            "QA_REVIEW": "#93370d",
            "COMPLETED": "#027a48",
        }

        return format_html(
            '<strong style="color:{};">{}</strong>',
            colors.get(obj.status, "#475467"),
            obj.get_status_display(),
        )

    @admin.action(description="Generate sampling plans")
    def generate_sampling_plans(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.perform_systematic_random_sampling",
            lambda obj: obj.generate_sampling_plan(),
            "{} sampling plan(s) generated.",
            "Could not generate sampling plan",
        )

    @admin.action(description="Mark selected samples as sampled")
    def mark_selected_as_sampled(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.perform_systematic_random_sampling",
            lambda obj: obj.mark_sampled(
                performed_by=request.user,
            ),
            "{} sampling record(s) marked sampled.",
            "Could not mark sampled",
        )

    @admin.action(description="Counter-check selected sampling records")
    def counter_check_selected(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.counter_check_systematic_sampling",
            lambda obj: obj.counter_check(
                performed_by=request.user,
            ),
            "{} sampling record(s) counter-checked.",
            "Could not counter-check",
        )

    @admin.action(description="Approve selected sampling deviations")
    def approve_selected_deviations(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.approve_sampling_weight_deviation",
            lambda obj: obj.approve_weight_deviation(
                performed_by=request.user,
            ),
            "{} sampling deviation(s) approved.",
            "Could not approve sampling deviation",
        )


@admin.register(SystematicRandomSample)
class SystematicRandomSampleAdmin(
    PlantScopedAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "sampling__batch__treatment_plant_id"

    list_display = (
        "sampling",
        "package_number",
        "declared_net_weight",
        "measured_weight",
        "weight_difference",
    )

    search_fields = (
        "sampling__batch__sample_id",
        "sampling__batch__batch_number",
        "sampling__batch__chemical__name",
    )

    list_filter = (
        "sampling__status",
        "sampling__qa_required",
        "sampling__qa_approved",
    )

    autocomplete_fields = (
        "sampling",
    )

    readonly_fields = (
        "package_number",
        "declared_net_weight",
        "weight_difference",
    )

    list_select_related = (
        "sampling",
        "sampling__batch",
        "sampling__batch__chemical",
        "sampling__batch__treatment_plant",
    )


@admin.register(ChemicalAnalysisProcess)
class ChemicalAnalysisProcessAdmin(
    PlantScopedAdminMixin,
    WorkflowAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "batch__treatment_plant_id"

    list_display = (
        "process_link",
        "sample_id_display",
        "chemical",
        "treatment_plant",
        "workflow_stage",
        "analysis_progress_display",
        "performed_by_display",
        "qa_officer",
        "approver",
        "overdue_badge",
        "created_at",
    )

    search_fields = (
        "batch__sample_id",
        "batch__batch_number",
        "batch__chemical__name",
        "batch__chemical__code",
        "assigned_analyst__username",
        "assigned_analyst__first_name",
        "assigned_analyst__last_name",
        "qa_officer__username",
        "approver__username",
    )

    list_filter = (
        "status",
        "batch__chemical",
        "batch__treatment_plant",
        "assigned_analyst",
        "qa_officer",
        "approver",
        DateRangeFilter,
    )

    autocomplete_fields = (
        "batch",
        "analysis_request",
        "initiated_by",
        "assigned_analyst",
        "qa_officer",
        "approver",
    )

    readonly_fields = (
        "batch",
        "analysis_request",
        "status",
        "initiated_by",
        "assigned_analyst",
        "qa_officer",
        "approver",
        "started_at",
        "checklist_completed_at",
        "analysis_started_at",
        "analysis_completed_at",
        "qa_reviewed_at",
        "approved_at",
        "completed_at",
        "rework_count",
        "created_at",
        "updated_at",
        "progress_bar",
        "current_assigned_analysts_display",
    )

    actions = (
        "start_selected_analysis",
        "complete_selected_analysis",
        "approve_selected_analysis",
    )

    list_select_related = (
        "batch",
        "batch__chemical",
        "batch__supplier",
        "batch__treatment_plant",
        "analysis_request",
        "initiated_by",
        "assigned_analyst",
        "qa_officer",
        "approver",
    )

    fieldsets = (
        (
            "Workflow",
            {
                "fields": (
                    "batch",
                    "analysis_request",
                    "status",
                    "progress_bar",
                )
            },
        ),
        (
            "Analyst Assignment",
            {
                "fields": (
                    "current_assigned_analysts_display",
                    "assigned_analyst",
                )
            },
        ),
        (
            "Execution and Approval",
            {
                "fields": (
                    "initiated_by",
                    "qa_officer",
                    "approver",
                )
            },
        ),
        (
            "Lifecycle",
            {
                "fields": (
                    "started_at",
                    "checklist_completed_at",
                    "analysis_started_at",
                    "analysis_completed_at",
                    "qa_reviewed_at",
                    "approved_at",
                    "completed_at",
                    "rework_count",
                )
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Process")
    def process_link(self, obj):
        url = reverse(
            "admin:ca_chemicalanalysisprocess_change",
            args=[obj.pk],
        )

        return format_html(
            '<a href="{}"><strong>Process #{}</strong></a>',
            url,
        )

    @admin.display(description="Sample")
    def sample_id_display(self, obj):
        return obj.sample_id or "—"

    @admin.display(description="Plant")
    def treatment_plant(self, obj):
        return obj.treatment_plant or "—"

    @admin.display(description="Stage")
    def workflow_stage(self, obj):
        colors = {
            "CREATED": "#667085",
            "RECEIVED": "#175cd3",
            "REQUESTED": "#175cd3",
            "CHECKLIST": "#7f56d9",
            "SYSTEMATIC_RANDOM_SAMPLING": "#6941c6",
            "ANALYSIS": "#b54708",
            "RETEST": "#93370d",
            "QA": "#c11574",
            "APPROVED": "#027a48",
            "REJECTED": "#b42318",
            "UTILIZED": "#344054",
            "RETURNED": "#93370d",
            "COMPLETED": "#027a48",
        }

        return format_html(
            '<strong style="color:{};">{}</strong>',
            colors.get(obj.status, "#475467"),
            obj.get_status_display(),
        )

    @admin.display(description="Progress")
    def analysis_progress_display(self, obj):
        progress = obj.analysis_progress

        if progress is None:
            return "—"

        try:
            percentage = float(progress)
        except (
            TypeError,
            ValueError,
        ):
            return str(progress)

        percentage = max(
            0,
            min(100, percentage),
        )

        return format_html(
            '<div style="min-width:120px;">'
            '<div style="font-size:11px;margin-bottom:3px;">{}%</div>'
            '<div style="height:7px;background:#eaecf0;border-radius:5px;">'
            '<div style="height:7px;width:{}%;background:#175cd3;border-radius:5px;"></div>'
            "</div>"
            "</div>",
            int(percentage),
            int(percentage),
        )

    @admin.display(description="Performed by")
    def performed_by_display(self, obj):
        analyst = obj.assigned_analyst

        if analyst is None:
            return format_html(
                '<span style="color:#667085;">Not started</span>'
            )

        return format_html(
            "{} ({})",
            analyst.get_full_name() or analyst.username,
            analyst.username,
        )

    @admin.display(description="Current analysts")
    def current_assigned_analysts_display(self, obj):
        if not obj.analysis_request_id:
            return format_html(
                '<span style="color:#667085;">No analysis request</span>'
            )

        analysts = obj.analysis_request.assigned_analysts.filter(
            is_active=True,
        ).order_by(
            "first_name",
            "last_name",
            "username",
        )

        if not analysts.exists():
            return format_html(
                '<strong style="color:#b42318;">'
                "No analysts currently assigned through weekly duty tasks"
                "</strong>"
            )

        return format_html(
            "<br>".join(
                "{} — {}".format(
                    analyst.get_full_name() or analyst.username,
                    analyst.username,
                )
                for analyst in analysts
            )
        )

    @admin.display(description="Overdue")
    def overdue_badge(self, obj):
        if obj.is_overdue:
            return format_html(
                '<strong style="color:#b42318;">OVERDUE</strong>'
            )

        return format_html(
            '<strong style="color:#027a48;">ON TRACK</strong>'
        )

    @admin.action(description="Start selected chemical analyses")
    def start_selected_analysis(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.start_chemical_analysis",
            lambda obj: obj.mark_analysis_started(
                performed_by=request.user,
            ),
            "{} analysis process(es) started.",
            "Could not start analysis",
        )

    @admin.action(description="Complete selected chemical analyses")
    def complete_selected_analysis(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.complete_chemical_analysis",
            lambda obj: obj.mark_analysis_completed(
                performed_by=request.user,
            ),
            "{} analysis process(es) completed.",
            "Could not complete analysis",
        )

    @admin.action(description="Approve selected analysis processes")
    def approve_selected_analysis(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.approve_chemical_batch",
            lambda obj: obj.mark_approved(
                approved_by=request.user,
            ),
            "{} analysis process(es) approved.",
            "Could not approve analysis",
        )

    @admin.display(description="Progress")
    def progress_bar(self, obj):
        progress = obj.analysis_progress

        try:
            percentage = float(progress)
        except (
            TypeError,
            ValueError,
        ):
            percentage = 0

        percentage = max(
            0,
            min(100, percentage),
        )

        return format_html(
            '<div style="max-width:500px;">'
            "<strong>{}%</strong>"
            '<div style="height:10px;background:#eaecf0;'
            'border-radius:6px;margin-top:5px;">'
            '<div style="height:10px;width:{}%;'
            'background:#175cd3;border-radius:6px;"></div>'
            "</div>"
            "</div>",
            int(percentage),
            int(percentage),
        )


@admin.register(BatchTestResult)
class BatchTestResultAdmin(
    PlantScopedAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "batch__treatment_plant_id"

    list_display = (
        "batch",
        "parameter",
        "value_display",
        "status_badge",
        "analyst",
        "tested_at",
        "input_status",
    )

    search_fields = (
        "batch__sample_id",
        "batch__batch_number",
        "batch__chemical__name",
        "parameter__parameter_name",
        "analyst__username",
        "textual_result",
    )

    list_filter = (
        "status",
        "parameter__chemical",
        "analyst",
        "batch__treatment_plant",
        DateRangeFilter,
    )

    autocomplete_fields = (
        "batch",
        "parameter",
        "analyst",
    )

    readonly_fields = (
        "tested_at",
        "auto_remark",
    )

    list_select_related = (
        "batch",
        "batch__chemical",
        "batch__treatment_plant",
        "parameter",
        "parameter__chemical",
        "parameter__method",
        "analyst",
    )

    fieldsets = (
        (
            "Result",
            {
                "fields": (
                    "batch",
                    "parameter",
                    "value",
                    "textual_result",
                    "status",
                )
            },
        ),
        (
            "Execution",
            {
                "fields": (
                    "analyst",
                    "tested_at",
                    "auto_remark",
                )
            },
        ),
    )

    @admin.display(description="Value")
    def value_display(self, obj):
        if obj.value is not None:
            return obj.value

        if obj.textual_result:
            return obj.textual_result

        return "—"

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            BatchTestResult.Status.PASS: "#027a48",
            BatchTestResult.Status.FAIL: "#b42318",
            BatchTestResult.Status.NA: "#667085",
        }

        label = (
            obj.get_status_display()
            if obj.status
            else "Pending"
        )

        return format_html(
            '<strong style="color:{};">{}</strong>',
            colors.get(
                obj.status,
                "#b54708",
            ),
            label,
        )

    @admin.display(description="Method inputs")
    def input_status(self, obj):
        if hasattr(obj, "inputs"):
            return format_html(
                '<strong style="color:#027a48;">Present</strong>'
            )

        return format_html(
            '<span style="color:#667085;">None</span>'
        )


@admin.register(ChemicalAnalysisInput)
class ChemicalAnalysisInputAdmin(
    PlantScopedAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "test_result__batch__treatment_plant_id"

    list_display = (
        "test_result",
        "test_parameter_display",
        "analysis_method_display",
        "calculated_value",
        "input_count",
        "test_result_status",
    )

    search_fields = (
        "test_result__batch__sample_id",
        "test_result__parameter__parameter_name",
        "test_result__parameter__chemical__name",
    )

    list_filter = (
        "test_result__status",
        "test_result__parameter__chemical",
        "test_result__batch__treatment_plant",
    )

    autocomplete_fields = (
        "test_result",
    )

    readonly_fields = (
        "calculated_value",
        "required_fields_display",
        "formula_display",
        "rounding_precision_display",
    )

    fieldsets = (
        (
            "Test",
            {
                "fields": (
                    "test_result",
                    "required_fields_display",
                    "formula_display",
                    "rounding_precision_display",
                )
            },
        ),
        (
            "Analytical Inputs",
            {
                "fields": (
                    "inputs",
                    "calculated_value",
                )
            },
        ),
    )

    list_select_related = (
        "test_result",
        "test_result__batch",
        "test_result__parameter",
        "test_result__parameter__chemical",
        "test_result__parameter__method",
    )

    @admin.display(description="Parameter")
    def test_parameter_display(self, obj):
        return obj.test_parameter or "—"

    @admin.display(description="Method")
    def analysis_method_display(self, obj):
        return obj.analysis_method or "—"

    @admin.display(description="Inputs")
    def input_count(self, obj):
        if not isinstance(obj.inputs, dict):
            return 0

        return len(obj.inputs)

    @admin.display(description="Result")
    def test_result_status(self, obj):
        result = obj.test_result

        if not result:
            return "—"

        return (
            result.get_status_display()
            if result.status
            else "Pending"
        )

    @admin.display(description="Required fields")
    def required_fields_display(self, obj):
        fields = obj.required_input_fields

        return (
            ", ".join(fields)
            if fields
            else "None"
        )

    @admin.display(description="Formula")
    def formula_display(self, obj):
        return obj.formula or "None"

    @admin.display(description="Precision")
    def rounding_precision_display(self, obj):
        precision = obj.rounding_precision

        return (
            str(precision)
            if precision is not None
            else "Default"
        )


@admin.register(ChemicalCoA)
class ChemicalCoAAdmin(
    PlantScopedAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = "batch__treatment_plant_id"

    list_display = (
        "coa_link",
        "chemical_name",
        "supplier_name",
        "treatment_plant_display",
        "generation_badge",
        "approval_badge",
        "integrity_badge",
        "date_of_report",
        "approved_on",
    )

    search_fields = (
        "chemical_name",
        "supplier_name",
        "batch__sample_id",
        "batch__batch_number",
        "delivery_note_number",
        "verified_hash",
        "approved_by__username",
    )

    list_filter = (
        IntegrityFilter,
        "packaging_status",
        "approved_by",
        "batch__chemical",
        "batch__supplier",
        "batch__treatment_plant",
        DateRangeFilter,
    )

    autocomplete_fields = (
        "batch",
        "packaging_status",
        "approved_by",
    )

    readonly_fields = (
        "chemical_name",
        "supplier_name",
        "quantity",
        "delivered_to",
        "delivery_date",
        "delivery_note_number",
        "sampling_date",
        "analysis_date",
        "approved_by",
        "approved_on",
        "date_of_report",
        "updated_at",
        "verified_hash",
        "sample_id_display",
        "integrity_display",
        "generation_display",
        "result_statistics_display",
    )

    actions = (
        "prepare_selected_coas",
        "approve_selected_coas",
        "verify_selected_coas",
        "revoke_selected_approvals",
        "regenerate_selected_content",
    )

    list_select_related = (
        "batch",
        "batch__chemical",
        "batch__supplier",
        "batch__treatment_plant",
        "packaging_status",
        "approved_by",
    )

    fieldsets = (
        (
            "Certificate Identity",
            {
                "fields": (
                    "batch",
                    "sample_id_display",
                    "title",
                )
            },
        ),
        (
            "Report Content",
            {
                "fields": (
                    "coa_header",
                    "coa_footer",
                    "results_summary",
                    "remarks",
                )
            },
        ),
        (
            "Generated Data",
            {
                "fields": (
                    "chemical_name",
                    "supplier_name",
                    "quantity",
                    "delivered_to",
                    "delivery_date",
                    "delivery_note_number",
                    "packaging_status",
                    "sampling_date",
                    "analysis_date",
                )
            },
        ),
        (
            "Assets",
            {
                "fields": (
                    "footer_image",
                    "watermark",
                    "qr_code",
                    "pdf_file",
                )
            },
        ),
        (
            "Verification",
            {
                "fields": (
                    "generation_display",
                    "result_statistics_display",
                    "approved_by",
                    "approved_on",
                    "verified_hash",
                    "integrity_display",
                )
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    "date_of_report",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="CoA")
    def coa_link(self, obj):
        url = reverse(
            "admin:ca_chemicalcoa_change",
            args=[obj.pk],
        )

        return format_html(
            '<a href="{}"><strong>COA #{}</strong></a>',
            url,
        )

    @admin.display(description="Plant")
    def treatment_plant_display(self, obj):
        return obj.treatment_plant or "—"

    @admin.display(description="Generation")
    def generation_badge(self, obj):
        status = obj.generation_status

        if status in {
            "APPROVED",
            "READY",
        }:
            color = "#027a48"
        elif status in {
            "PENDING_PDF",
            "PENDING_QR",
            "PENDING_WATERMARK",
        }:
            color = "#b54708"
        else:
            color = "#b42318"

        return format_html(
            '<strong style="color:{};">{}</strong>',
            color,
            status,
        )

    @admin.display(description="Approval")
    def approval_badge(self, obj):
        if obj.is_approved:
            return format_html(
                '<strong style="color:#027a48;">APPROVED</strong>'
            )

        return format_html(
            '<strong style="color:#b54708;">PENDING</strong>'
        )

    @admin.display(description="Integrity")
    def integrity_badge(self, obj):
        status = obj.integrity_status

        colors = {
            "VALID": "#027a48",
            "UNVERIFIED": "#b54708",
            "UNAPPROVED": "#667085",
            "INVALID": "#b42318",
        }

        return format_html(
            '<strong style="color:{};">{}</strong>',
            colors.get(
                status,
                "#475467",
            ),
            status,
        )

    @admin.display(description="Sample")
    def sample_id_display(self, obj):
        return obj.sample_id or "—"

    @admin.display(description="Integrity")
    def integrity_display(self, obj):
        return obj.integrity_status

    @admin.display(description="Generation")
    def generation_display(self, obj):
        return obj.generation_status

    @admin.display(description="Statistics")
    def result_statistics_display(self, obj):
        statistics = obj.get_result_statistics()

        return format_html(
            "Total: {} | Pass: {} | Fail: {} | "
            "N/A: {} | Pending: {} | Pass rate: {}%",
            statistics["total"],
            statistics["pass"],
            statistics["fail"],
            statistics["na"],
            statistics["pending"],
            statistics["pass_rate"],
        )

    @admin.action(description="Prepare selected CoAs")
    def prepare_selected_coas(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.generate_chemical_coa",
            lambda obj: obj.prepare_for_generation(),
            "{} CoA(s) prepared.",
            "Could not prepare CoA",
        )

    @admin.action(description="Approve selected CoAs")
    def approve_selected_coas(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.approve_chemical_coa",
            lambda obj: obj.approve(
                approved_by=request.user,
            ),
            "{} CoA(s) approved.",
            "Could not approve CoA",
        )

    @admin.action(description="Verify selected CoAs")
    def verify_selected_coas(self, request, queryset):
        self._permission_required(
            request,
            "ca.verify_chemical_coa",
        )

        success = 0

        for obj in queryset:
            try:
                if not obj.is_approved:
                    raise ValidationError(
                        "Only approved CoAs can be verified."
                    )

                if obj.verify_integrity():
                    success += 1
                else:
                    self.message_user(
                        request,
                        f"Integrity verification failed for CoA #{obj.pk}.",
                        level=messages.ERROR,
                    )
            except ValidationError as exc:
                self.message_user(
                    request,
                    f"CoA #{obj.pk}: {exc}",
                    level=messages.ERROR,
                )

        if success:
            self.message_user(
                request,
                f"{success} CoA(s) passed integrity verification.",
                level=messages.SUCCESS,
            )

    @admin.action(description="Revoke selected CoA approvals")
    def revoke_selected_approvals(self, request, queryset):
        self._permission_required(
            request,
            "ca.approve_chemical_coa",
        )

        success = 0

        for obj in queryset:
            try:
                with transaction.atomic():
                    obj.revoke_approval()
                success += 1
            except ValidationError as exc:
                self.message_user(
                    request,
                    f"CoA #{obj.pk}: {exc}",
                    level=messages.ERROR,
                )

        if success:
            self.message_user(
                request,
                f"{success} CoA approval(s) revoked.",
                level=messages.SUCCESS,
            )

    @admin.action(description="Regenerate selected CoA content")
    def regenerate_selected_content(self, request, queryset):
        self._run_action(
            request,
            queryset,
            "ca.generate_chemical_coa",
            lambda obj: obj.regenerate_content(),
            "{} CoA(s) regenerated.",
            "Could not regenerate CoA",
        )


@admin.register(
    ChecklistForWaterTreatmentChemicalAnalysis
)
class ChecklistForWaterTreatmentChemicalAnalysisAdmin(
    PlantScopedAdminMixin,
    WorkflowAdminMixin,
    admin.ModelAdmin,
):
    plant_lookup = (
        "chemical_analysis_request__batch__treatment_plant_id"
    )

    list_display = (
        "checklist_link",
        "sample_id_display",
        "chemical",
        "treatment_plant_display",
        "grade",
        "net_weight_display",
        "expiry_badge",
        "completion_badge",
        "sampled_by",
        "completed_by",
        "created_at",
    )

    search_fields = (
        "chemical__name",
        "chemical__code",
        "chemical_analysis_request__request_id",
        "chemical_analysis_request__batch__sample_id",
        "chemical_analysis_request__batch__batch_number",
        "sampled_by__username",
        "requested_by__username",
        "completed_by__username",
        "storage_conditions",
        "country_of_origin",
    )

    list_filter = (
        "completed",
        "grade",
        ExpiryFilter,
        "chemical",
        "chemical_analysis_request__batch__treatment_plant",
        DateRangeFilter,
    )

    autocomplete_fields = (
        "chemical_analysis_request",
        "chemical",
        "sampled_by",
        "requested_by",
        "completed_by",
    )

    readonly_fields = (
        "completed_at",
        "completed_by",
        "created_at",
        "updated_at",
        "sample_id_display",
        "batch_number_display",
        "treatment_plant_display",
        "analysis_status_display",
        "expiry_status_display",
        "days_until_expiry_display",
    )

    actions = (
        "complete_selected_checklists",
        "reopen_selected_checklists",
    )

    list_select_related = (
        "chemical",
        "chemical_analysis_request",
        "chemical_analysis_request__batch",
        "chemical_analysis_request__batch__treatment_plant",
        "sampled_by",
        "requested_by",
        "completed_by",
    )

    fieldsets = (
        (
            "Workflow Context",
            {
                "fields": (
                    "chemical_analysis_request",
                    "sample_id_display",
                    "batch_number_display",
                    "treatment_plant_display",
                    "analysis_status_display",
                )
            },
        ),
        (
            "Chemical Verification",
            {
                "fields": (
                    "chemical",
                    "manufacturer_name_indicated",
                    "chemical_name_on_label",
                    "min_mass_indicated",
                    "grade",
                    "manufacture_date",
                    "expiry_date",
                    "expiry_status_display",
                    "days_until_expiry_display",
                )
            },
        ),
        (
            "Receipt Conditions",
            {
                "fields": (
                    "storage_conditions",
                    "net_weight",
                    "country_of_origin",
                    "handling_instructions",
                )
            },
        ),
        (
            "Hazard Assessment",
            {
                "fields": (
                    "is_oxidizing",
                    "is_corrosive",
                    "may_cause_fire",
                    "contact_with_acids_liberates_toxic_gas",
                    "causes_burns",
                    "keep_out_of_reach_of_children",
                    "contact_with_eyes_action",
                    "fire_action_requires_respiratory_equipment",
                )
            },
        ),
        (
            "Personnel",
            {
                "fields": (
                    "sampled_by",
                    "requested_by",
                )
            },
        ),
        (
            "Completion",
            {
                "fields": (
                    "completed",
                    "completed_at",
                    "completed_by",
                )
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Checklist")
    def checklist_link(self, obj):
        url = reverse(
            "admin:ca_checklistforwatertreatmentchemicalanalysis_change",
            args=[obj.pk],
        )

        return format_html(
            '<a href="{}"><strong>Checklist #{}</strong></a>',
            url,
        )

    @admin.display(description="Sample")
    def sample_id_display(self, obj):
        return obj.sample_id or "—"

    @admin.display(description="Batch")
    def batch_number_display(self, obj):
        return obj.batch_number or "—"

    @admin.display(description="Plant")
    def treatment_plant_display(self, obj):
        return obj.treatment_plant or "—"

    @admin.display(description="Analysis")
    def analysis_status_display(self, obj):
        status = obj.analysis_status

        if not status:
            return "—"

        return status

    @admin.display(description="Weight")
    def net_weight_display(self, obj):
        return f"{obj.net_weight:g}"

    @admin.display(description="Expiry")
    def expiry_badge(self, obj):
        status = obj.expiry_status

        colors = {
            "VALID": "#027a48",
            "EXPIRING_SOON": "#b54708",
            "EXPIRES_TODAY": "#b42318",
            "EXPIRED": "#b42318",
            "UNKNOWN": "#667085",
        }

        return format_html(
            '<strong style="color:{};">{}</strong>',
            colors.get(
                status,
                "#475467",
            ),
            status.replace("_", " "),
        )

    @admin.display(description="Completion")
    def completion_badge(self, obj):
        if obj.completed:
            return format_html(
                '<strong style="color:#027a48;">COMPLETED</strong>'
            )

        return format_html(
            '<strong style="color:#b54708;">PENDING</strong>'
        )

    @admin.display(description="Expiry")
    def expiry_status_display(self, obj):
        return obj.expiry_status

    @admin.display(description="Days to expiry")
    def days_until_expiry_display(self, obj):
        days = obj.days_until_expiry

        if days is None:
            return "—"

        return days

    @admin.action(description="Complete selected checklists")
    def complete_selected_checklists(
        self,
        request,
        queryset,
    ):
        self._run_action(
            request,
            queryset,
            "ca.complete_receiving_checklist",
            lambda obj: obj.mark_completed(
                performed_by=request.user,
            ),
            "{} checklist(s) completed.",
            "Could not complete checklist",
        )

    @admin.action(description="Reopen selected checklists")
    def reopen_selected_checklists(
        self,
        request,
        queryset,
    ):
        self._run_action(
            request,
            queryset,
            "ca.reopen_chemical_checklist",
            lambda obj: obj.reopen(
                performed_by=request.user,
            ),
            "{} checklist(s) reopened.",
            "Could not reopen checklist",
        )