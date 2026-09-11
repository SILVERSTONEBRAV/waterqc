
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import (
    ChemicalBatchForm,
    ChemicalSpecificationFilterForm,
    TestResultFilterForm,
)
from .models import (
    BatchTestResult,
    ChemicalAnalysisInput,
    ChemicalAnalysisProcess,
    ChemicalAnalysisRequest,
    ChemicalBatch,
    ChemicalCoA,
    ChemicalSpecification,
    ChecklistForWaterTreatmentChemicalAnalysis,
)


User = get_user_model()


CHEMICAL_PERMISSIONS = {
    "view_workflow": "ca.view_chemicalanalysisprocess",
    "receive": "ca.receive_chemical_batch",
    "request": "ca.create_analysis_request",
    "checklist": "ca.complete_receiving_checklist",
    "sampling": "ca.perform_systematic_random_sampling",
    "sampling_counter_check": "ca.counter_check_systematic_sampling",
    "sampling_qa": "ca.approve_sampling_weight_deviation",
    "start": "ca.start_chemical_analysis",
    "result": "ca.record_chemical_result",
    "complete": "ca.complete_chemical_analysis",
    "retest": "ca.perform_chemical_retest",
    "qa": "ca.review_chemical_analysis",
    "generate_coa": "ca.generate_chemical_coa",
    "verify_coa": "ca.verify_chemical_coa",
    "approve_batch": "ca.approve_chemical_batch",
    "reject_batch": "ca.reject_chemical_batch",
    "utilize": "ca.utilize_chemical_batch",
    "return": "ca.return_chemical_batch",
    "reopen_checklist": "ca.reopen_chemical_checklist",
}


def user_has_permission(user, permission):
    if not user or not user.is_authenticated:
        return False

    return user.has_perm(permission)


def user_has_any_permission(user, permissions):
    if not user or not user.is_authenticated:
        return False

    return any(
        user.has_perm(permission)
        for permission in permissions
    )


def ensure_permission(user, permission):
    if not user or not user.is_authenticated:
        raise PermissionDenied

    if not user.has_perm(permission):
        raise PermissionDenied


def ensure_any_permission(user, permissions):
    if not user_has_any_permission(user, permissions):
        raise PermissionDenied


def get_user_plant_id(user):
    if not user or not user.is_authenticated:
        return None

    if user.is_superuser:
        return None

    plant = getattr(
        user,
        "assigned_treatment_plant",
        None,
    )

    if plant is None:
        return None

    return getattr(
        plant,
        "pk",
        None,
    )


def user_can_access_plant(user, plant_id):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    assigned_plant_id = get_user_plant_id(user)

    if assigned_plant_id is None or plant_id is None:
        return False

    return assigned_plant_id == plant_id


def user_can_access_batch(user, batch):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if batch is None:
        return False

    return user_can_access_plant(
        user,
        batch.treatment_plant_id,
    )


def user_can_access_request(user, request_obj):
    if request_obj is None:
        return False

    return user_can_access_batch(
        user,
        request_obj.batch,
    )


def user_can_access_process(user, process):
    if process is None:
        return False

    return user_can_access_batch(
        user,
        process.batch,
    )


def get_process_queryset_for_user(user):
    queryset = (
        ChemicalAnalysisProcess.objects
        .select_related(
            "batch",
            "batch__chemical",
            "batch__supplier",
            "batch__treatment_plant",
            "analysis_request",
            "analysis_request__location",
            "initiated_by",
            "assigned_analyst",
            "qa_officer",
            "approver",
        )
        .prefetch_related(
            "batch__test_results",
            "analysis_request__assigned_analysts",
        )
    )

    if user.is_superuser:
        return queryset

    plant_id = get_user_plant_id(user)

    if plant_id is None:
        return queryset.none()

    return queryset.filter(
        batch__treatment_plant_id=plant_id,
    )


def get_batch_queryset_for_user(user):
    queryset = (
        ChemicalBatch.objects
        .select_related(
            "chemical",
            "supplier",
            "treatment_plant",
            "received_by",
        )
        .prefetch_related(
            "test_results",
        )
    )

    if user.is_superuser:
        return queryset

    plant_id = get_user_plant_id(user)

    if plant_id is None:
        return queryset.none()

    return queryset.filter(
        treatment_plant_id=plant_id,
    )


def get_request_queryset_for_user(user):
    queryset = (
        ChemicalAnalysisRequest.objects
        .select_related(
            "batch",
            "batch__chemical",
            "batch__supplier",
            "batch__treatment_plant",
            "location",
            "requested_by",
            "received_by",
            "completed_by",
        )
        .prefetch_related(
            "assigned_analysts",
        )
    )

    if user.is_superuser:
        return queryset

    plant_id = get_user_plant_id(user)

    if plant_id is None:
        return queryset.none()

    return queryset.filter(
        batch__treatment_plant_id=plant_id,
    )


def get_checklist_queryset_for_user(user):
    queryset = (
        ChecklistForWaterTreatmentChemicalAnalysis.objects
        .select_related(
            "chemical_analysis_request",
            "chemical_analysis_request__batch",
            "chemical_analysis_request__batch__treatment_plant",
            "chemical",
            "sampled_by",
            "requested_by",
            "completed_by",
        )
    )

    if user.is_superuser:
        return queryset

    plant_id = get_user_plant_id(user)

    if plant_id is None:
        return queryset.none()

    return queryset.filter(
        chemical_analysis_request__batch__treatment_plant_id=plant_id,
    )


def get_result_queryset_for_user(user):
    queryset = (
        BatchTestResult.objects
        .select_related(
            "batch",
            "batch__chemical",
            "batch__treatment_plant",
            "parameter",
            "parameter__chemical",
            "parameter__method",
            "analyst",
        )
    )

    if user.is_superuser:
        return queryset

    plant_id = get_user_plant_id(user)

    if plant_id is None:
        return queryset.none()

    return queryset.filter(
        batch__treatment_plant_id=plant_id,
    )


def get_coa_queryset_for_user(user):
    queryset = (
        ChemicalCoA.objects
        .select_related(
            "batch",
            "batch__chemical",
            "batch__supplier",
            "batch__treatment_plant",
            "packaging_status",
            "approved_by",
        )
        .prefetch_related(
            "batch__test_results",
        )
    )

    if user.is_superuser:
        return queryset

    plant_id = get_user_plant_id(user)

    if plant_id is None:
        return queryset.none()

    return queryset.filter(
        batch__treatment_plant_id=plant_id,
    )


def get_input_queryset_for_user(user):
    queryset = (
        ChemicalAnalysisInput.objects
        .select_related(
            "test_result",
            "test_result__batch",
            "test_result__batch__chemical",
            "test_result__batch__treatment_plant",
            "test_result__parameter",
            "test_result__parameter__chemical",
            "test_result__parameter__method",
            "test_result__analyst",
        )
    )

    if user.is_superuser:
        return queryset

    plant_id = get_user_plant_id(user)

    if plant_id is None:
        return queryset.none()

    return queryset.filter(
        test_result__batch__treatment_plant_id=plant_id,
    )


class ChemicalWorkflowAccessMixin(LoginRequiredMixin):
    permission_required = None
    any_permission_required = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if self.permission_required:
            ensure_permission(
                request.user,
                self.permission_required,
            )

        if self.any_permission_required:
            ensure_any_permission(
                request.user,
                self.any_permission_required,
            )

        return super().dispatch(
            request,
            *args,
            **kwargs,
        )


class DashboardView(
    ChemicalWorkflowAccessMixin,
    TemplateView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/dashboard/pages/dashboard.html"
    permission_required = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user = self.request.user
        now = timezone.now()
        today = timezone.localdate()

        process_queryset = get_process_queryset_for_user(user)
        request_queryset = get_request_queryset_for_user(user)
        batch_queryset = get_batch_queryset_for_user(user)
        result_queryset = get_result_queryset_for_user(user)
        coa_queryset = get_coa_queryset_for_user(user)

        status_counts = dict(
            process_queryset
            .values("status")
            .annotate(count=Count("pk"))
            .values_list("status", "count")
        )

        active_statuses = {
            ChemicalAnalysisProcess.WorkflowStatus.CREATED,
            ChemicalAnalysisProcess.WorkflowStatus.RECEIVED,
            ChemicalAnalysisProcess.WorkflowStatus.REQUESTED,
            ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST,
            ChemicalAnalysisProcess.WorkflowStatus.SYSTEMATIC_RANDOM_SAMPLING,
            ChemicalAnalysisProcess.WorkflowStatus.ANALYSIS,
            ChemicalAnalysisProcess.WorkflowStatus.RETEST,
            ChemicalAnalysisProcess.WorkflowStatus.QA,
            ChemicalAnalysisProcess.WorkflowStatus.APPROVED,
        }

        pending_results_filter = (
            Q(status__isnull=True)
            | Q(status="")
        )

        context.update(
            {
                "processes": process_queryset[:25],
                "recent_processes": process_queryset[:10],
                "status_counts": status_counts,
                "total_processes": process_queryset.count(),
                "active_processes": process_queryset.filter(
                    status__in=active_statuses,
                ).count(),
                "created_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.CREATED,
                    0,
                ),
                "received_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.RECEIVED,
                    0,
                ),
                "requested_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.REQUESTED,
                    0,
                ),
                "checklist_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST,
                    0,
                ),
                "sampling_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.SYSTEMATIC_RANDOM_SAMPLING,
                    0,
                ),
                "analysis_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.ANALYSIS,
                    0,
                ),
                "retest_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.RETEST,
                    0,
                ),
                "qa_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.QA,
                    0,
                ),
                "approved_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.APPROVED,
                    0,
                ),
                "rejected_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.REJECTED,
                    0,
                ),
                "utilized_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.UTILIZED,
                    0,
                ),
                "returned_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.RETURNED,
                    0,
                ),
                "completed_count": status_counts.get(
                    ChemicalAnalysisProcess.WorkflowStatus.COMPLETED,
                    0,
                ),
                "total_batches": batch_queryset.count(),
                "received_batches": batch_queryset.filter(
                    status=ChemicalBatch.Status.RECEIVED,
                ).count(),
                "analysed_batches": batch_queryset.filter(
                    status=ChemicalBatch.Status.ANALYSED,
                ).count(),
                "approved_batches": batch_queryset.filter(
                    status=ChemicalBatch.Status.APPROVED,
                ).count(),
                "rejected_batches": batch_queryset.filter(
                    status=ChemicalBatch.Status.REJECTED,
                ).count(),
                "utilized_batches": batch_queryset.filter(
                    status=ChemicalBatch.Status.UTILIZED,
                ).count(),
                "returned_batches": batch_queryset.filter(
                    status=ChemicalBatch.Status.RETURNED,
                ).count(),
                "pending_requests": request_queryset.filter(
                    status=ChemicalAnalysisRequest.Status.PENDING,
                ).count(),
                "in_progress_requests": request_queryset.filter(
                    status=ChemicalAnalysisRequest.Status.IN_PROGRESS,
                ).count(),
                "completed_requests": request_queryset.filter(
                    status=ChemicalAnalysisRequest.Status.COMPLETED,
                ).count(),
                "overdue_requests": (
                    request_queryset
                    .filter(analysis_deadline__lt=now)
                    .exclude(
                        status=ChemicalAnalysisRequest.Status.COMPLETED,
                    )
                    .count()
                ),
                "total_results": result_queryset.count(),
                "pending_results": result_queryset.filter(
                    pending_results_filter,
                ).count(),
                "passed_results": result_queryset.filter(
                    status=BatchTestResult.Status.PASS,
                ).count(),
                "failed_results": result_queryset.filter(
                    status=BatchTestResult.Status.FAIL,
                ).count(),
                "na_results": result_queryset.filter(
                    status=BatchTestResult.Status.NA,
                ).count(),
                "total_coas": coa_queryset.count(),
                "approved_coas": coa_queryset.filter(
                    approved_on__isnull=False,
                ).count(),
                "today": today,
                "now": now,
                "can_create_batch": user.has_perm(
                    "ca.add_chemicalbatch",
                ),
                "can_receive": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["receive"],
                ),
                "can_create_request": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["request"],
                ),
                "can_complete_checklist": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["checklist"],
                ),
                "can_sampling": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["sampling"],
                ),
                "can_sampling_counter_check": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["sampling_counter_check"],
                ),
                "can_sampling_qa": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["sampling_qa"],
                ),
                "can_start_analysis": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["start"],
                ),
                "can_record_result": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["result"],
                ),
                "can_complete_analysis": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["complete"],
                ),
                "can_retest": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["retest"],
                ),
                "can_review": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["qa"],
                ),
                "can_verify_coa": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["verify_coa"],
                ),
                "can_approve_batch": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["approve_batch"],
                ),
                "can_reject_batch": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["reject_batch"],
                ),
                "can_utilize": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["utilize"],
                ),
                "can_return": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["return"],
                ),
                "can_reopen_checklist": user_has_permission(
                    user,
                    CHEMICAL_PERMISSIONS["reopen_checklist"],
                ),
                "can_analyse": user_has_any_permission(
                    user,
                    (
                        CHEMICAL_PERMISSIONS["start"],
                        CHEMICAL_PERMISSIONS["result"],
                        CHEMICAL_PERMISSIONS["complete"],
                    ),
                ),
                "can_manage_workflow": user_has_any_permission(
                    user,
                    (
                        CHEMICAL_PERMISSIONS["receive"],
                        CHEMICAL_PERMISSIONS["request"],
                        CHEMICAL_PERMISSIONS["checklist"],
                        CHEMICAL_PERMISSIONS["sampling"],
                        CHEMICAL_PERMISSIONS["sampling_counter_check"],
                        CHEMICAL_PERMISSIONS["sampling_qa"],
                        CHEMICAL_PERMISSIONS["start"],
                        CHEMICAL_PERMISSIONS["result"],
                        CHEMICAL_PERMISSIONS["complete"],
                        CHEMICAL_PERMISSIONS["retest"],
                        CHEMICAL_PERMISSIONS["qa"],
                        CHEMICAL_PERMISSIONS["verify_coa"],
                        CHEMICAL_PERMISSIONS["approve_batch"],
                        CHEMICAL_PERMISSIONS["reject_batch"],
                        CHEMICAL_PERMISSIONS["utilize"],
                        CHEMICAL_PERMISSIONS["return"],
                    ),
                ),
            }
        )

        return context


class ChemicalBatchListView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = ChemicalBatch
    template_name = "ca/chema/batch_list.html"
    context_object_name = "batches"
    paginate_by = 50
    permission_required = "ca.view_chemicalbatch"

    def get_queryset(self):
        queryset = get_batch_queryset_for_user(
            self.request.user,
        )

        status = self.request.GET.get("status")
        chemical = self.request.GET.get("chemical")
        query = self.request.GET.get("q")

        if status:
            queryset = queryset.filter(status=status)

        if chemical:
            queryset = queryset.filter(chemical_id=chemical)

        if query:
            queryset = queryset.filter(
                Q(sample_id__icontains=query)
                | Q(batch_number__icontains=query)
                | Q(delivery_note_number__icontains=query)
                | Q(chemical__name__icontains=query)
                | Q(supplier__name__icontains=query)
            )

        return queryset.order_by(
            "-created_at",
            "-pk",
        )


class ChemicalBatchDetailView(
    ChemicalWorkflowAccessMixin,
    DetailView,
):
    model = ChemicalBatch
    template_name = "ca/chema/batch_detail.html"
    context_object_name = "batch"
    permission_required = "ca.view_chemicalbatch"

    def get_queryset(self):
        return get_batch_queryset_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch = self.object

        context["results"] = (
            batch.test_results
            .select_related(
                "parameter",
                "parameter__chemical",
                "parameter__method",
                "analyst",
            )
            .order_by(
                "parameter__parameter_name",
                "id",
            )
        )

        context["process"] = getattr(
            batch,
            "analysis_process",
            None,
        )

        context["analysis_request"] = getattr(
            batch,
            "analysis_request",
            None,
        )

        context["coa"] = getattr(
            batch,
            "coa",
            None,
        )

        return context


class ChemicalBatchCreateView(
    ChemicalWorkflowAccessMixin,
    CreateView,
):
    model = ChemicalBatch
    form_class = ChemicalBatchForm
    template_name = "ca/chema/batch_form.html"
    permission_required = "ca.add_chemicalbatch"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        batch = form.save(commit=False)

        if not batch.received_by_id:
            batch.received_by = self.request.user

        if not self.request.user.is_superuser:
            if not user_can_access_plant(
                self.request.user,
                batch.treatment_plant_id,
            ):
                form.add_error(
                    "treatment_plant",
                    "You cannot create a batch for this treatment plant.",
                )
                return self.form_invalid(form)

        batch.save()
        form.save_m2m()
        self.object = batch

        messages.success(
            self.request,
            f"Chemical batch {batch.sample_id} was created.",
        )

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse(
            "ca:batch-detail",
            kwargs={"pk": self.object.pk},
        )


class ChemicalBatchUpdateView(
    ChemicalWorkflowAccessMixin,
    UpdateView,
):
    model = ChemicalBatch
    form_class = ChemicalBatchForm
    template_name = "ca/chema/batch_form.html"
    context_object_name = "batch"
    permission_required = "ca.change_chemicalbatch"

    def get_queryset(self):
        return get_batch_queryset_for_user(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse(
            "ca:batch-detail",
            kwargs={"pk": self.object.pk},
        )


class ChemicalAnalysisRequestListView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = ChemicalAnalysisRequest
    template_name = "ca/chema/request_list.html"
    context_object_name = "requests"
    paginate_by = 50
    permission_required = "ca.view_chemicalanalysisrequest"

    def get_queryset(self):
        queryset = get_request_queryset_for_user(
            self.request.user,
        )

        status = self.request.GET.get("status")
        query = self.request.GET.get("q")
        overdue = self.request.GET.get("overdue")

        if status:
            queryset = queryset.filter(status=status)

        if query:
            queryset = queryset.filter(
                Q(request_id__icontains=query)
                | Q(batch__sample_id__icontains=query)
                | Q(batch__batch_number__icontains=query)
                | Q(batch__chemical__name__icontains=query)
            )

        if overdue:
            queryset = (
                queryset
                .filter(analysis_deadline__lt=timezone.now())
                .exclude(
                    status=ChemicalAnalysisRequest.Status.COMPLETED,
                )
            )

        return queryset.order_by(
            "-created_at",
            "-pk",
        )


class ChemicalAnalysisRequestDetailView(
    ChemicalWorkflowAccessMixin,
    DetailView,
):
    model = ChemicalAnalysisRequest
    template_name = "ca/chema/request_detail.html"
    context_object_name = "analysis_request"
    permission_required = "ca.view_chemicalanalysisrequest"

    def get_queryset(self):
        return get_request_queryset_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request_obj = self.object

        context["checklists"] = (
            request_obj.checklists
            .select_related(
                "chemical",
                "sampled_by",
                "requested_by",
                "completed_by",
            )
            .order_by("-created_at")
        )

        context["results"] = (
            request_obj.batch.test_results
            .select_related(
                "parameter",
                "parameter__method",
                "analyst",
            )
            .order_by(
                "parameter__parameter_name",
                "id",
            )
        )

        context["process"] = getattr(
            request_obj,
            "analysis_process",
            None,
        )

        context["assigned_analysts"] = (
            request_obj.get_current_assigned_analysts()
        )

        return context


class ProcessListView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/process/process_list.html"
    context_object_name = "processes"
    paginate_by = 50
    permission_required = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_queryset(self):
        queryset = get_process_queryset_for_user(
            self.request.user,
        )

        status = self.request.GET.get("status")
        query = self.request.GET.get("q")

        if status:
            queryset = queryset.filter(status=status)

        if query:
            queryset = queryset.filter(
                Q(batch__sample_id__icontains=query)
                | Q(batch__batch_number__icontains=query)
                | Q(batch__chemical__name__icontains=query)
                | Q(
                    analysis_request__request_id__icontains=query,
                )
            )

        return queryset.order_by(
            "-created_at",
            "-pk",
        )


class ProcessDetailView(
    ChemicalWorkflowAccessMixin,
    DetailView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/process/process_detail.html"
    context_object_name = "process"
    permission_required = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_queryset(self):
        return get_process_queryset_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        process = self.object

        results = (
            process.test_results
            .select_related(
                "parameter",
                "parameter__chemical",
                "parameter__method",
                "analyst",
            )
            .order_by(
                "parameter__parameter_name",
                "id",
            )
        )

        context.update(
            {
                "results": results,
                "pending_tests": process.pending_tests,
                "completed_tests": process.completed_tests,
                "failed_tests": process.failed_tests,
                "progress": process.analysis_progress,
                "required_test_count": process.required_test_count,
                "completed_test_count": process.completed_test_count,
                "passed_test_count": process.passed_test_count,
                "is_analysis_complete": process.is_analysis_complete,
                "has_pending_tests": process.has_pending_tests,
                "is_overdue": process.is_overdue,
                "checklist": process.get_latest_checklist(),
                "analysis_request": process.analysis_request,
                "coa": getattr(
                    process.batch,
                    "coa",
                    None,
                ),
                "workflow_status_label": (
                    process.get_status_display()
                    if hasattr(process, "get_status_display")
                    else process.status
                ),
                "assigned_analysts": (
                    process.assigned_analysts
                    if hasattr(process, "assigned_analysts")
                    else process.analysis_request.get_current_assigned_analysts()
                ),
                "has_assigned_analysts": (
                    process.has_assigned_analysts
                    if hasattr(process, "has_assigned_analysts")
                    else process.analysis_request.get_current_assigned_analysts().exists()
                ),
                "is_current_user_assigned_analyst": (
                    process.is_authorized_analyst(self.request.user)
                    if hasattr(process, "is_authorized_analyst")
                    else process.analysis_request.is_assigned_analyst(
                        self.request.user,
                    )
                ),
            }
        )

        return context


class ProcessJSONView(
    ChemicalWorkflowAccessMixin,
    View,
):
    permission_required = CHEMICAL_PERMISSIONS["view_workflow"]

    def get(self, request, pk, *args, **kwargs):
        process = get_object_or_404(
            get_process_queryset_for_user(request.user),
            pk=pk,
        )

        assigned_analysts = (
            process.assigned_analysts
            if hasattr(process, "assigned_analysts")
            else process.analysis_request.assigned_analysts.all()
        )

        results = list(
            process.test_results
            .select_related(
                "parameter",
                "parameter__parameter_name",
                "parameter__chemical",
                "parameter__method",
                "analyst",
            )
            .values(
                "id",
                "parameter_id",
                "parameter__parameter_name",
                "value",
                "textual_result",
                "status",
                "tested_at",
                "analyst_id",
            )
        )

        for result in results:
            if result["tested_at"]:
                result["tested_at"] = result["tested_at"].isoformat()

        return JsonResponse(
            {
                "id": process.pk,
                "status": process.status,
                "status_label": (
                    process.get_status_display()
                    if hasattr(process, "get_status_display")
                    else process.status
                ),
                "sample_id": getattr(
                    process,
                    "sample_id",
                    getattr(
                        process.batch,
                        "sample_id",
                        None,
                    ),
                ),
                "batch_number": getattr(
                    process,
                    "batch_number",
                    getattr(
                        process.batch,
                        "batch_number",
                        None,
                    ),
                ),
                "chemical": (
                    process.batch.chemical.name
                    if process.batch
                    and process.batch.chemical
                    else None
                ),
                "progress": process.analysis_progress,
                "required_tests": process.required_test_count,
                "completed_tests": process.completed_test_count,
                "passed_tests": process.passed_test_count,
                "pending_tests": process.pending_tests.count(),
                "failed_tests": process.failed_tests.count(),
                "is_analysis_complete": process.is_analysis_complete,
                "is_overdue": process.is_overdue,
                "assigned_analysts": [
                    {
                        "id": analyst.pk,
                        "username": analyst.username,
                        "name": (
                            analyst.get_full_name()
                            or analyst.username
                        ),
                    }
                    for analyst in assigned_analysts
                ],
                "is_current_user_assigned_analyst": (
                    process.is_authorized_analyst(request.user)
                    if hasattr(process, "is_authorized_analyst")
                    else process.analysis_request.is_assigned_analyst(
                        request.user,
                    )
                ),
                "assigned_analyst_id": (
                    process.assigned_analyst_id
                ),
                "results": results,
            }
        )


class ChemicalAnalysisInputDetailView(
    ChemicalWorkflowAccessMixin,
    DetailView,
):
    model = ChemicalAnalysisInput
    template_name = "ca/chema/analysis_input_detail.html"
    context_object_name = "analysis_input"
    permission_required = "ca.view_chemicalanalysisinput"

    def get_queryset(self):
        return get_input_queryset_for_user(self.request.user)


class RecalculateAnalysisInputView(
    ChemicalWorkflowAccessMixin,
    View,
):
    permission_required = CHEMICAL_PERMISSIONS["result"]

    def post(self, request, pk, *args, **kwargs):
        analysis_input = get_object_or_404(
            get_input_queryset_for_user(request.user),
            pk=pk,
        )

        with transaction.atomic():
            analysis_input = (
                ChemicalAnalysisInput.objects
                .select_for_update()
                .select_related(
                    "test_result",
                    "test_result__batch",
                    "test_result__parameter",
                    "test_result__parameter__method",
                )
                .get(pk=analysis_input.pk)
            )

            if not user_can_access_batch(
                request.user,
                analysis_input.test_result.batch,
            ):
                raise PermissionDenied

            if hasattr(analysis_input, "recalculate"):
                analysis_input.recalculate()
            else:
                analysis_input.calculate()

            analysis_input.save()

        messages.success(
            request,
            "Analysis input recalculated.",
        )

        return redirect(
            "ca:analysis-input-detail",
            pk=analysis_input.pk,
        )


class ChemicalSpecificationListView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = ChemicalSpecification
    template_name = "ca/chema/specification_list.html"
    context_object_name = "specifications"
    paginate_by = 100
    permission_required = "ca.view_chemicalspecification"

    def get_queryset(self):
        queryset = (
            ChemicalSpecification.objects
            .select_related(
                "chemical",
                "method",
                "treatment_plant",
            )
            .prefetch_related("remarks")
        )

        if not self.request.user.is_superuser:
            plant_id = get_user_plant_id(self.request.user)

            if plant_id is None:
                return queryset.none()

            queryset = queryset.filter(
                treatment_plant_id=plant_id,
            )

        chemical = self.request.GET.get("chemical")
        query = self.request.GET.get("q")

        if chemical:
            queryset = queryset.filter(
                chemical_id=chemical,
            )

        if query:
            queryset = queryset.filter(
                Q(parameter_name__icontains=query)
                | Q(chemical__name__icontains=query)
            )

        return queryset.order_by(
            "chemical__name",
            "parameter_name",
            "version",
        )


class ChemicalSpecificationFilterView(
    ChemicalWorkflowAccessMixin,
    View,
):
    permission_required = "ca.view_chemicalspecification"

    def get(self, request, *args, **kwargs):
        form = ChemicalSpecificationFilterForm(
            request.GET or None,
        )

        queryset = (
            ChemicalSpecification.objects
            .select_related(
                "chemical",
                "method",
                "treatment_plant",
            )
            .prefetch_related("remarks")
        )

        if not request.user.is_superuser:
            plant_id = get_user_plant_id(request.user)

            if plant_id is None:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(
                    treatment_plant_id=plant_id,
                )

        if form.is_valid():
            chemical = form.cleaned_data.get("chemical")
            parameter = form.cleaned_data.get("parameter")
            treatment_plant = form.cleaned_data.get("treatment_plant")

            if chemical:
                queryset = queryset.filter(chemical=chemical)

            if parameter:
                queryset = queryset.filter(
                    parameter_name__icontains=parameter,
                )

            if treatment_plant:
                queryset = queryset.filter(
                    treatment_plant=treatment_plant,
                )

        return JsonResponse(
            {
                "results": list(
                    queryset.values(
                        "id",
                        "parameter_name",
                        "version",
                        "is_required",
                        "min_limit",
                        "max_limit",
                        "chemical__name",
                        "method__name",
                        "treatment_plant__name",
                    )
                )
            }
        )


class ResultListView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = BatchTestResult
    template_name = "ca/chema/result_list.html"
    context_object_name = "results"
    paginate_by = 100
    permission_required = "ca.view_batchtestresult"

    def get_queryset(self):
        queryset = get_result_queryset_for_user(
            self.request.user,
        )

        status = self.request.GET.get("status")
        query = self.request.GET.get("q")

        if status:
            queryset = queryset.filter(status=status)

        if query:
            queryset = queryset.filter(
                Q(batch__sample_id__icontains=query)
                | Q(parameter__parameter_name__icontains=query)
                | Q(batch__chemical__name__icontains=query)
            )

        return queryset.order_by(
            "-tested_at",
            "-pk",
        )


class ResultDetailView(
    ChemicalWorkflowAccessMixin,
    DetailView,
):
    model = BatchTestResult
    template_name = "ca/chema/result_detail.html"
    context_object_name = "result"
    permission_required = "ca.view_batchtestresult"

    def get_queryset(self):
        return get_result_queryset_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["analysis_input"] = (
            ChemicalAnalysisInput.objects
            .filter(test_result=self.object)
            .first()
        )

        return context


class ChemicalCoAListView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = ChemicalCoA
    template_name = "ca/chema/coa_list.html"
    context_object_name = "coas"
    paginate_by = 50
    permission_required = "ca.view_chemicalcoa"

    def get_queryset(self):
        queryset = get_coa_queryset_for_user(
            self.request.user,
        )

        query = self.request.GET.get("q")
        status = self.request.GET.get("status")

        if query:
            queryset = queryset.filter(
                Q(chemical_name__icontains=query)
                | Q(supplier_name__icontains=query)
                | Q(batch__sample_id__icontains=query)
            )

        if status == "approved":
            queryset = queryset.filter(
                approved_on__isnull=False,
            )
        elif status == "pending":
            queryset = queryset.filter(
                approved_on__isnull=True,
            )

        return queryset.order_by(
            "-date_of_report",
            "-pk",
        )


class ChemicalCoADetailView(
    ChemicalWorkflowAccessMixin,
    DetailView,
):
    model = ChemicalCoA
    template_name = "ca/chema/coa_detail.html"
    context_object_name = "coa"
    permission_required = "ca.view_chemicalcoa"

    def get_queryset(self):
        return get_coa_queryset_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        coa = self.object

        context.update(
            {
                "results": coa.get_results(),
                "result_counts": coa.get_result_counts(),
                "statistics": coa.get_result_statistics(),
                "verification_payload": coa.get_verification_payload(),
            }
        )

        return context


class RegenerateChemicalCoAView(
    ChemicalWorkflowAccessMixin,
    View,
):
    permission_required = CHEMICAL_PERMISSIONS["generate_coa"]

    def post(self, request, pk, *args, **kwargs):
        coa = get_object_or_404(
            get_coa_queryset_for_user(request.user),
            pk=pk,
        )

        with transaction.atomic():
            coa = (
                ChemicalCoA.objects
                .select_for_update()
                .get(pk=coa.pk)
            )

            if coa.is_approved:
                raise ValidationError(
                    "An approved Certificate of Analysis cannot be regenerated.",
                )

            coa.regenerate_content()

            coa.save(
                populate=False,
                regenerate_watermark=False,
                regenerate_hash=False,
                generate_assets=True,
            )

        messages.success(
            request,
            "Chemical Certificate of Analysis regenerated.",
        )

        return redirect(
            "ca:coa-detail",
            pk=coa.pk,
        )


class VerifyChemicalCoAView(
    ChemicalWorkflowAccessMixin,
    View,
):
    permission_required = CHEMICAL_PERMISSIONS["verify_coa"]

    def get(self, request, pk, *args, **kwargs):
        coa = get_object_or_404(
            get_coa_queryset_for_user(request.user),
            pk=pk,
        )

        return JsonResponse(
            {
                "coa": coa.get_verification_payload(),
                "integrity": coa.integrity_status,
                "valid": coa.verify_integrity(),
            }
        )


class DownloadChemicalCoAView(
    ChemicalWorkflowAccessMixin,
    View,
):
    permission_required = "ca.view_chemicalcoa"

    def get(self, request, pk, *args, **kwargs):
        coa = get_object_or_404(
            get_coa_queryset_for_user(request.user),
            pk=pk,
        )

        if not coa.pdf_file:
            raise Http404(
                "The Certificate of Analysis PDF has not been generated.",
            )

        return redirect(coa.pdf_file.url)


class ReopenChecklistView(
    ChemicalWorkflowAccessMixin,
    View,
):
    permission_required = CHEMICAL_PERMISSIONS["reopen_checklist"]

    def post(self, request, pk, *args, **kwargs):
        checklist = get_object_or_404(
            get_checklist_queryset_for_user(request.user),
            pk=pk,
        )

        checklist.reopen(
            performed_by=request.user,
        )

        messages.success(
            request,
            "Checklist reopened.",
        )

        process = getattr(
            checklist.chemical_analysis_request,
            "analysis_process",
            None,
        )

        if process is None:
            raise Http404(
                "No analysis process is associated with this checklist.",
            )

        return redirect(
            "ca:process-detail",
            pk=process.pk,
        )


class ChecklistDetailView(
    ChemicalWorkflowAccessMixin,
    DetailView,
):
    model = ChecklistForWaterTreatmentChemicalAnalysis
    template_name = "ca/chema/checklist_detail.html"
    context_object_name = "checklist"
    permission_required = (
        "ca.view_checklistforwatertreatmentchemicalanalysis"
    )

    def get_queryset(self):
        return get_checklist_queryset_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["process"] = getattr(
            self.object.chemical_analysis_request,
            "analysis_process",
            None,
        )

        return context


class ChecklistListView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = ChecklistForWaterTreatmentChemicalAnalysis
    template_name = "ca/chema/checklist_list.html"
    context_object_name = "checklists"
    paginate_by = 50
    permission_required = (
        "ca.view_checklistforwatertreatmentchemicalanalysis"
    )

    def get_queryset(self):
        queryset = get_checklist_queryset_for_user(
            self.request.user,
        )

        completed = self.request.GET.get("completed")
        query = self.request.GET.get("q")

        if completed == "1":
            queryset = queryset.filter(completed=True)
        elif completed == "0":
            queryset = queryset.filter(completed=False)

        if query:
            queryset = queryset.filter(
                Q(chemical__name__icontains=query)
                | Q(
                    chemical_analysis_request__request_id__icontains=query,
                )
                | Q(
                    chemical_analysis_request__batch__sample_id__icontains=query,
                )
            )

        return queryset.order_by(
            "-created_at",
            "-pk",
        )


class ProcessStatisticsView(
    ChemicalWorkflowAccessMixin,
    View,
):
    permission_required = CHEMICAL_PERMISSIONS["view_workflow"]

    def get(self, request, *args, **kwargs):
        process_queryset = get_process_queryset_for_user(
            request.user,
        )
        request_queryset = get_request_queryset_for_user(
            request.user,
        )
        result_queryset = get_result_queryset_for_user(
            request.user,
        )
        now = timezone.now()

        statuses = dict(
            process_queryset
            .values("status")
            .annotate(count=Count("pk"))
            .values_list("status", "count")
        )

        result_counts = {
            "total": result_queryset.count(),
            "pass": result_queryset.filter(
                status=BatchTestResult.Status.PASS,
            ).count(),
            "fail": result_queryset.filter(
                status=BatchTestResult.Status.FAIL,
            ).count(),
            "na": result_queryset.filter(
                status=BatchTestResult.Status.NA,
            ).count(),
            "pending": result_queryset.filter(
                Q(status__isnull=True)
                | Q(status=""),
            ).count(),
        }

        return JsonResponse(
            {
                "generated_at": now.isoformat(),
                "processes": {
                    "total": process_queryset.count(),
                    "statuses": statuses,
                },
                "requests": {
                    "total": request_queryset.count(),
                    "pending": request_queryset.filter(
                        status=ChemicalAnalysisRequest.Status.PENDING,
                    ).count(),
                    "in_progress": request_queryset.filter(
                        status=ChemicalAnalysisRequest.Status.IN_PROGRESS,
                    ).count(),
                    "completed": request_queryset.filter(
                        status=ChemicalAnalysisRequest.Status.COMPLETED,
                    ).count(),
                    "overdue": (
                        request_queryset
                        .filter(analysis_deadline__lt=now)
                        .exclude(
                            status=ChemicalAnalysisRequest.Status.COMPLETED,
                        )
                        .count()
                    ),
                },
                "results": result_counts,
            }
        )


class ProcessRefreshView(
    ChemicalWorkflowAccessMixin,
    View,
):
    permission_required = CHEMICAL_PERMISSIONS["view_workflow"]

    def get(self, request, pk, *args, **kwargs):
        process = get_object_or_404(
            get_process_queryset_for_user(request.user),
            pk=pk,
        )

        return JsonResponse(
            {
                "id": process.pk,
                "status": process.status,
                "progress": process.analysis_progress,
                "required_test_count": process.required_test_count,
                "completed_test_count": process.completed_test_count,
                "passed_test_count": process.passed_test_count,
                "pending_tests": process.pending_tests.count(),
                "failed_tests": process.failed_tests.count(),
                "is_analysis_complete": process.is_analysis_complete,
                "is_overdue": process.is_overdue,
                "assigned_analyst_id": process.assigned_analyst_id,
                "is_current_user_assigned_analyst": (
                    process.is_authorized_analyst(request.user)
                    if hasattr(process, "is_authorized_analyst")
                    else process.analysis_request.is_assigned_analyst(
                        request.user,
                    )
                ),
            }
        )

    def post(self, request, pk, *args, **kwargs):
        return self.get(
            request,
            pk,
            *args,
            **kwargs,
        )


class MyChemicalTasksView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/chema/my_tasks.html"
    context_object_name = "processes"
    paginate_by = 50
    permission_required = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_queryset(self):
        queryset = get_process_queryset_for_user(
            self.request.user,
        )
        user = self.request.user
        filters = Q()

        analyst_permissions = (
            CHEMICAL_PERMISSIONS["start"],
            CHEMICAL_PERMISSIONS["result"],
            CHEMICAL_PERMISSIONS["complete"],
        )

        if user_has_any_permission(
            user,
            analyst_permissions,
        ):
            filters |= Q(
                analysis_request__assigned_analysts=user,
            )
            filters |= Q(
                assigned_analyst=user,
            )

        if user_has_permission(
            user,
            CHEMICAL_PERMISSIONS["qa"],
        ):
            filters |= Q(
                qa_officer=user,
            )

        if user_has_permission(
            user,
            CHEMICAL_PERMISSIONS["approve_batch"],
        ):
            filters |= Q(
                approver=user,
            )

        if not filters:
            return queryset.none()

        return (
            queryset
            .filter(filters)
            .distinct()
            .order_by(
                "-updated_at",
                "-pk",
            )
        )


class OverdueAnalysisView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = ChemicalAnalysisRequest
    template_name = "ca/chema/overdue_analysis.html"
    context_object_name = "requests"
    paginate_by = 50
    permission_required = "ca.view_chemicalanalysisrequest"

    def get_queryset(self):
        return (
            get_request_queryset_for_user(self.request.user)
            .filter(analysis_deadline__lt=timezone.now())
            .exclude(
                status=ChemicalAnalysisRequest.Status.COMPLETED,
            )
            .order_by(
                "analysis_deadline",
                "-pk",
            )
        )


class PendingAnalysisView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/chema/pending_analysis.html"
    context_object_name = "processes"
    paginate_by = 50
    permission_required = CHEMICAL_PERMISSIONS["start"]

    def get_queryset(self):
        return (
            get_process_queryset_for_user(self.request.user)
            .filter(
                status__in={
                    ChemicalAnalysisProcess.WorkflowStatus.SYSTEMATIC_RANDOM_SAMPLING,
                    ChemicalAnalysisProcess.WorkflowStatus.ANALYSIS,
                    ChemicalAnalysisProcess.WorkflowStatus.RETEST,
                },
            )
            .filter(
                Q(
                    analysis_request__assigned_analysts=self.request.user,
                )
                | Q(
                    assigned_analyst=self.request.user,
                )
            )
            .distinct()
            .order_by(
                "-updated_at",
                "-pk",
            )
        )


class PendingApprovalView(
    ChemicalWorkflowAccessMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/chema/pending_approval.html"
    context_object_name = "processes"
    paginate_by = 50
    permission_required = CHEMICAL_PERMISSIONS["approve_batch"]

    def get_queryset(self):
        return (
            get_process_queryset_for_user(self.request.user)
            .filter(
                status=ChemicalAnalysisProcess.WorkflowStatus.QA,
                qa_reviewed_at__isnull=False,
            )
            .order_by(
                "-updated_at",
                "-pk",
            )
        )
