from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from core.engine.super_user import SuperUserEngine

from .forms import (
    ChemicalBatchForm,
    ChemicalSpecificationFilterForm,
    TestResultFilterForm,
)
from .mixins import CaWanjalaMixin
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


CHEMICAL_PERMISSIONS = {
    "view_workflow": "ca.view_chemicalanalysisprocess",
    "receive": "ca.receive_chemical_batch",
    "request": "ca.create_analysis_request",
    "checklist": "ca.complete_receiving_checklist",
    "start": "ca.start_chemical_analysis",
    "result": "ca.record_chemical_result",
    "complete": "ca.complete_chemical_analysis",
    "retest": "ca.perform_chemical_retest",
    "qa": "ca.review_chemical_analysis",
    "generate_coa": "ca.approve_chemical_coa",
    "approve_coa": "ca.approve_chemical_coa",
    "verify_coa": "ca.verify_chemical_coa",
    "approve_batch": "ca.approve_chemical_batch",
    "reject_batch": "ca.reject_chemical_batch",
    "utilize": "ca.utilize_chemical_batch",
    "return": "ca.return_chemical_batch",
    "reopen_checklist": "ca.reopen_chemical_checklist",
}


PROCESS_ACTIVE_STATUSES = (
    "REQUESTED",
    "CHECKLIST",
    "ASSIGNED",
    "ANALYSIS",
    "RETEST",
    "QA",
)

PROCESS_ANALYSIS_STATUSES = (
    "ANALYSIS",
    "RETEST",
)

PROCESS_TERMINAL_STATUSES = (
    "UTILIZED",
    "RETURNED",
    "COMPLETED",
)

BATCH_TERMINAL_STATUSES = (
    "UTILIZED",
    "RETURNED",
)


def _scope_queryset(queryset, user, field="treatment_plant_id", plant_id=None):
    """Plant-scope a queryset using Wanjala/SuperUser rules."""
    if SuperUserEngine.is_superuser(user):
        if plant_id is None:
            return queryset
        return queryset.filter(**{field: plant_id})

    assigned = getattr(user, "assigned_treatment_plant_id", None)
    if assigned is None:
        raise PermissionDenied(
            "Your account is not assigned to a treatment plant."
        )
    return queryset.filter(**{field: assigned})


def _process_queryset(user, plant_id=None):
    queryset = ChemicalAnalysisProcess.objects.all()

    return _scope_queryset(
        queryset,
        user,
        "batch__treatment_plant_id",
        plant_id=plant_id,
    )


def _process_display_queryset(user, plant_id=None):
    return (
        _process_queryset(user, plant_id=plant_id)
        .select_related(
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
        .prefetch_related(
            "analysis_request__assigned_analysts",
        )
        .order_by(
            "-updated_at",
            "-pk",
        )
    )


def _batch_queryset(user, plant_id=None):
    queryset = ChemicalBatch.objects.all()

    return _scope_queryset(
        queryset,
        user,
        plant_id=plant_id,
    )


def _batch_display_queryset(user, plant_id=None):
    return (
        _batch_queryset(user, plant_id=plant_id)
        .select_related(
            "chemical",
            "supplier",
            "treatment_plant",
            "received_by",
        )
        .order_by(
            "-received_date",
            "-pk",
        )
    )


def _request_queryset(user, plant_id=None):
    queryset = ChemicalAnalysisRequest.objects.all()

    return _scope_queryset(
        queryset,
        user,
        "batch__treatment_plant_id",
        plant_id=plant_id,
    )


def _request_display_queryset(user, plant_id=None):
    return (
        _request_queryset(user, plant_id=plant_id)
        .select_related(
            "batch",
            "batch__chemical",
            "batch__supplier",
            "batch__treatment_plant",
            "requested_by",
            "received_by",
        )
        .prefetch_related(
            "assigned_analysts",
        )
        .order_by(
            "-created_at",
            "-pk",
        )
    )


def _result_queryset(user, plant_id=None):
    queryset = BatchTestResult.objects.all()

    return _scope_queryset(
        queryset,
        user,
        "batch__treatment_plant_id",
        plant_id=plant_id,
    )


def _result_display_queryset(user, plant_id=None):
    return (
        _result_queryset(user, plant_id=plant_id)
        .select_related(
            "batch",
            "batch__chemical",
            "parameter",
            "parameter__method",
            "analyst",
        )
        .order_by(
            "-tested_at",
            "-pk",
        )
    )


def _analysis_input_queryset(user, plant_id=None):
    queryset = (
        ChemicalAnalysisInput.objects
        .select_related(
            "test_result",
            "test_result__batch",
            "test_result__batch__chemical",
            "test_result__parameter",
            "test_result__parameter__method",
        )
    )

    return _scope_queryset(
        queryset,
        user,
        "test_result__batch__treatment_plant_id",
        plant_id=plant_id,
    )


def _coa_queryset(user, plant_id=None):
    queryset = ChemicalCoA.objects.all()

    return _scope_queryset(
        queryset,
        user,
        "batch__treatment_plant_id",
        plant_id=plant_id,
    )


def _coa_display_queryset(user, plant_id=None):
    return (
        _coa_queryset(user, plant_id=plant_id)
        .select_related(
            "batch",
            "batch__chemical",
            "batch__supplier",
            "batch__treatment_plant",
            "approved_by",
        )
        .order_by(
            "-pk",
        )
    )


def _specification_queryset(user, plant_id=None):
    queryset = (
        ChemicalSpecification.objects
        .select_related(
            "chemical",
            "method",
            "treatment_plant",
        )
        .order_by(
            "chemical__name",
            "parameter_name",
            "-version",
        )
    )

    if SuperUserEngine.is_superuser(user):
        if plant_id is None:
            return queryset
        return queryset.filter(
            Q(treatment_plant_id=plant_id)
            | Q(treatment_plant__isnull=True)
        )

    assigned = getattr(user, "assigned_treatment_plant_id", None)
    if assigned is None:
        raise PermissionDenied(
            "Your account is not assigned to a treatment plant."
        )

    return queryset.filter(
        Q(treatment_plant_id=assigned)
        | Q(treatment_plant__isnull=True)
    )


def _checklist_queryset(user, plant_id=None):
    queryset = (
        ChecklistForWaterTreatmentChemicalAnalysis.objects
        .select_related(
            "chemical_analysis_request",
            "chemical_analysis_request__batch",
            "chemical_analysis_request__batch__chemical",
            "chemical_analysis_request__batch__treatment_plant",
        )
        .order_by(
            "-pk",
        )
    )

    return _scope_queryset(
        queryset,
        user,
        "chemical_analysis_request__batch__treatment_plant_id",
        plant_id=plant_id,
    )


def _get_process_or_404(
    user,
    pk,
    lock=False,
):
    queryset = _process_display_queryset(user, plant_id=plant_id)

    if lock:
        queryset = queryset.select_for_update()

    process = (
        queryset
        .filter(pk=pk)
        .first()
    )

    if process is None:
        raise Http404(
            "Chemical analysis process not found."
        )

    return process


def _get_batch_or_404(
    user,
    pk,
    lock=False,
):
    queryset = _batch_display_queryset(user, plant_id=plant_id)

    if lock:
        queryset = queryset.select_for_update()

    batch = (
        queryset
        .filter(pk=pk)
        .first()
    )

    if batch is None:
        raise Http404(
            "Chemical batch not found."
        )

    return batch


def _get_request_or_404(
    user,
    pk,
):
    request_obj = (
        _request_display_queryset(user, plant_id=plant_id)
        .filter(pk=pk)
        .first()
    )

    if request_obj is None:
        raise Http404(
            "Chemical analysis request not found."
        )

    return request_obj


def _get_result_or_404(
    user,
    pk,
):
    result = (
        _result_display_queryset(user, plant_id=plant_id)
        .filter(pk=pk)
        .first()
    )

    if result is None:
        raise Http404(
            "Chemical test result not found."
        )

    return result


def _get_coa_or_404(
    user,
    pk,
    lock=False,
):
    queryset = _coa_display_queryset(user, plant_id=plant_id)

    if lock:
        queryset = queryset.select_for_update()

    coa = (
        queryset
        .filter(pk=pk)
        .first()
    )

    if coa is None:
        raise Http404(
            "Certificate of Analysis not found."
        )

    return coa




def _request_assignment_data(analysis_request):
    assigned_analysts = list(
        analysis_request.assigned_analysts.all()
    )

    deadline = getattr(
        analysis_request,
        "analysis_deadline",
        None,
    )

    return {
        "assigned_analyst_ids": [
            user.pk
            for user in assigned_analysts
        ],
        "assigned_analysts": [
            {
                "id": user.pk,
                "username": getattr(
                    user,
                    "username",
                    None,
                ),
                "name": (
                    user.get_full_name()
                    if hasattr(
                        user,
                        "get_full_name",
                    )
                    else str(user)
                ),
            }
            for user in assigned_analysts
        ],
        "assigned_analyst_count": len(
            assigned_analysts
        ),
        "assignment_pending": bool(
            getattr(
                analysis_request,
                "assignment_pending",
                False,
            )
        ),
        "assignment_overdue": bool(
            getattr(
                analysis_request,
                "assignment_overdue",
                False,
            )
        ),
        "manual_assigned_at": (
            analysis_request.manual_assigned_at.isoformat()
            if getattr(
                analysis_request,
                "manual_assigned_at",
                None,
            )
            else None
        ),
        "auto_assigned_at": (
            analysis_request.auto_assigned_at.isoformat()
            if getattr(
                analysis_request,
                "auto_assigned_at",
                None,
            )
            else None
        ),
        "analysis_deadline": (
            deadline.isoformat()
            if deadline
            else None
        ),
    }


class ChemicalBatchListView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalBatch
    template_name = "ca/chema/batch_list.html"
    context_object_name = "batches"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]
    paginate_by = 50

    def get_queryset(self):
        queryset = _batch_display_queryset(
            self.request.user
        )

        status = self.request.GET.get("status")

        if status:
            queryset = queryset.filter(
                status=status
            )

        chemical = self.request.GET.get(
            "chemical"
        )

        if chemical:
            queryset = queryset.filter(
                Q(
                    chemical__name__icontains=chemical
                )
                | Q(
                    chemical__code__icontains=chemical
                )
            )

        query = self.request.GET.get("q")

        if query:
            queryset = queryset.filter(
                Q(
                    sample_id__icontains=query
                )
                | Q(
                    batch_number__icontains=query
                )
                | Q(
                    delivery_note_number__icontains=query
                )
            )

        return queryset


class ChemicalBatchDetailView(
    CaWanjalaMixin,
    DetailView,
):
    model = ChemicalBatch
    template_name = "ca/chema/batch_detail.html"
    context_object_name = "batch"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_object(self, queryset=None):
        return _get_batch_or_404(
            self.request.user,
            self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(
            **kwargs
        )

        batch = self.object
        user = self.request.user

        process = (
            _process_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(batch=batch)
            .first()
        )

        results = (
            _result_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(batch=batch)
        )

        coa = (
            _coa_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(batch=batch)
            .first()
        )

        analysis_request = (
            _request_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(batch=batch)
            .first()
        )

        checklist = None

        if analysis_request:
            checklist = (
                _checklist_queryset(user, plant_id=self.get_scope_plant_id())
                .filter(
                    chemical_analysis_request=analysis_request
                )
                .first()
            )

        context.update(
            {
                "process": process,
                "analysis_request": analysis_request,
                "checklist": checklist,
                "results": results,
                "coa": coa,
                "sampling": None,
            }
        )

        return context


class ChemicalBatchCreateView(
    CaWanjalaMixin,
    CreateView,
):
    model = ChemicalBatch
    form_class = ChemicalBatchForm
    template_name = "ca/chema/batch_form.html"
    permission_required_view = CHEMICAL_PERMISSIONS["receive"]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = self.request.user

        if not self.is_ca_superuser():
            form.instance.treatment_plant_id = (
                getattr(user, "assigned_treatment_plant_id", None)
            )
            if form.instance.treatment_plant_id is None:
                raise PermissionDenied(
                    "Your account is not assigned to a treatment plant."
                )

        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "ca:batch-detail",
            kwargs={
                "pk": self.object.pk
            },
        )


class ChemicalBatchUpdateView(
    CaWanjalaMixin,
    UpdateView,
):
    model = ChemicalBatch
    form_class = ChemicalBatchForm
    template_name = "ca/chema/batch_form.html"
    permission_required_view = CHEMICAL_PERMISSIONS["receive"]

    def get_object(self, queryset=None):
        return _get_batch_or_404(
            self.request.user,
            self.kwargs["pk"],
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = self.request.user

        if not self.is_ca_superuser():
            plant_id = getattr(user, "assigned_treatment_plant_id", None)

            if plant_id is None:
                raise PermissionDenied(
                    "Your account is not assigned to a treatment plant."
                )

            if form.instance.treatment_plant_id != plant_id:
                raise PermissionDenied(
                    "The chemical batch belongs to another treatment plant."
                )

        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "ca:batch-detail",
            kwargs={
                "pk": self.object.pk
            },
        )


class ChemicalAnalysisRequestListView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalAnalysisRequest
    template_name = "ca/chema/request_list.html"
    context_object_name = "requests"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]
    paginate_by = 50

    def get_queryset(self):
        queryset = _request_display_queryset(
            self.request.user
        )

        status = self.request.GET.get(
            "status"
        )

        if status:
            queryset = queryset.filter(
                status=status
            )

        assignment = self.request.GET.get(
            "assignment"
        )

        if assignment == "pending":
            queryset = queryset.filter(
                assigned_analysts__isnull=True
            )

        elif assignment == "assigned":
            queryset = queryset.filter(
                assigned_analysts__isnull=False
            )

        elif assignment == "overdue":
            deadline_field = getattr(
                ChemicalAnalysisRequest,
                "assignment_deadline",
                None,
            )

            if deadline_field is not None:
                queryset = queryset.filter(
                    assignment_deadline__lt=timezone.now(),
                    assigned_analysts__isnull=True,
                )

        query = self.request.GET.get("q")

        if query:
            queryset = queryset.filter(
                Q(
                    batch__sample_id__icontains=query
                )
                | Q(
                    batch__batch_number__icontains=query
                )
                | Q(
                    batch__chemical__name__icontains=query
                )
            )

        return queryset.distinct()


class ChemicalAnalysisRequestDetailView(
    CaWanjalaMixin,
    DetailView,
):
    model = ChemicalAnalysisRequest
    template_name = "ca/chema/request_detail.html"
    context_object_name = "analysis_request"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_object(self, queryset=None):
        return _get_request_or_404(
            self.request.user,
            self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(
            **kwargs
        )

        request_obj = self.object
        user = self.request.user

        process = (
            _process_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(
                analysis_request=request_obj
            )
            .first()
        )

        checklist = (
            _checklist_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(
                chemical_analysis_request=request_obj
            )
            .first()
        )

        context.update(
            {
                "process": process,
                "checklist": checklist,
                "assignment": _request_assignment_data(
                    request_obj
                ),
                "assigned_analysts": (
                    request_obj.assigned_analysts.all()
                ),
                "assignment_pending": bool(
                    getattr(
                        request_obj,
                        "assignment_pending",
                        False,
                    )
                ),
                "assignment_overdue": bool(
                    getattr(
                        request_obj,
                        "assignment_overdue",
                        False,
                    )
                ),
            }
        )

        return context


class ProcessListView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/process/process_list.html"
    context_object_name = "processes"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]
    paginate_by = 50

    def get_queryset(self):
        queryset = _process_display_queryset(
            self.request.user
        )

        status = self.request.GET.get(
            "status"
        )

        if status:
            queryset = queryset.filter(
                status=status
            )

        query = self.request.GET.get("q")

        if query:
            queryset = queryset.filter(
                Q(
                    batch__sample_id__icontains=query
                )
                | Q(
                    batch__batch_number__icontains=query
                )
                | Q(
                    batch__chemical__name__icontains=query
                )
            )

        assignment = self.request.GET.get(
            "assignment"
        )

        if assignment == "assigned":
            queryset = queryset.filter(
                analysis_request__assigned_analysts__isnull=False
            )

        elif assignment == "unassigned":
            queryset = queryset.filter(
                analysis_request__assigned_analysts__isnull=True
            )

        return queryset.distinct()


class ProcessDetailView(
    CaWanjalaMixin,
    DetailView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/process/process_detail.html"
    context_object_name = "process"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_object(self, queryset=None):
        return _get_process_or_404(
            self.request.user,
            self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(
            **kwargs
        )

        process = self.object
        user = self.request.user

        results = (
            _result_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(batch=process.batch)
        )

        inputs = (
            _analysis_input_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(
                test_result__batch=process.batch
            )
            .order_by("-pk")
        )

        coa = (
            _coa_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(batch=process.batch)
            .first()
        )

        analysis_request = (
            getattr(
                process,
                "analysis_request",
                None,
            )
        )

        assigned_analysts = []

        if analysis_request:
            assigned_analysts = list(
                analysis_request.assigned_analysts.all()
            )

        context.update(
            {
                "results": results,
                "inputs": inputs,
                "sampling": None,
                "coa": coa,
                "pending_tests": process.pending_tests,
                "failed_tests": process.failed_tests,
                "is_analysis_complete": bool(
                    process.is_analysis_complete
                ),
                "assigned_analysts": assigned_analysts,
                "has_assigned_analysts": bool(
                    assigned_analysts
                ),
                "assignment_pending": bool(
                    getattr(
                        analysis_request,
                        "assignment_pending",
                        False,
                    )
                )
                if analysis_request
                else False,
                "assignment_overdue": bool(
                    getattr(
                        analysis_request,
                        "assignment_overdue",
                        False,
                    )
                )
                if analysis_request
                else False,
            }
        )

        return context


class ProcessJSONView(
    CaWanjalaMixin,
    View,
):
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]

    def get(self, request, *args, **kwargs):
        process = _get_process_or_404(
            request.user,
            kwargs["pk"],
        )

        results = list(
            _result_queryset(request.user)
            .filter(batch=process.batch)
            .values(
                "id",
                "parameter_id",
                "parameter__parameter_name",
                "status",
                "tested_at",
                "analyst_id",
                "value",
                "textual_result",
                "auto_remark",
            )
        )

        analysis_request = (
            getattr(
                process,
                "analysis_request",
                None,
            )
        )

        assignment = (
            _request_assignment_data(
                analysis_request
            )
            if analysis_request
            else {
                "assigned_analyst_ids": [],
                "assigned_analysts": [],
                "assigned_analyst_count": 0,
                "assignment_pending": False,
                "assignment_overdue": False,
                "manual_assigned_at": None,
                "auto_assigned_at": None,
                "analysis_deadline": None,
            }
        )

        coa = (
            _coa_display_queryset(request.user, plant_id=self.get_scope_plant_id())
            .filter(batch=process.batch)
            .first()
        )

        integrity_status = (
            getattr(
                coa,
                "integrity_status",
                None,
            )
            if coa
            else None
        )

        return JsonResponse(
            {
                "id": process.pk,
                "status": process.status,
                "batch_id": process.batch_id,
                "analysis_request_id": (
                    process.analysis_request_id
                ),
                "assigned_analyst_id": (
                    process.assigned_analyst_id
                ),
                "assigned_analysts": assignment[
                    "assigned_analysts"
                ],
                "assigned_analyst_ids": assignment[
                    "assigned_analyst_ids"
                ],
                "assigned_analyst_count": assignment[
                    "assigned_analyst_count"
                ],
                "assignment_pending": assignment[
                    "assignment_pending"
                ],
                "assignment_overdue": assignment[
                    "assignment_overdue"
                ],
                "manual_assigned_at": assignment[
                    "manual_assigned_at"
                ],
                "auto_assigned_at": assignment[
                    "auto_assigned_at"
                ],
                "analysis_deadline": assignment[
                    "analysis_deadline"
                ],
                "qa_officer_id": (
                    process.qa_officer_id
                ),
                "approver_id": (
                    process.approver_id
                ),
                "analysis_started_at": (
                    process.analysis_started_at.isoformat()
                    if process.analysis_started_at
                    else None
                ),
                "analysis_completed_at": (
                    process.analysis_completed_at.isoformat()
                    if process.analysis_completed_at
                    else None
                ),
                "is_analysis_complete": bool(
                    process.is_analysis_complete
                ),
                "has_pending_tests": bool(
                    process.has_pending_tests
                ),
                "pending_test_count": (
                    process.pending_tests.count()
                    if hasattr(
                        process.pending_tests,
                        "count",
                    )
                    else len(
                        process.pending_tests
                    )
                ),
                "failed_test_count": (
                    process.failed_tests.count()
                    if hasattr(
                        process.failed_tests,
                        "count",
                    )
                    else len(
                        process.failed_tests
                    )
                ),
                "coa": (
                    {
                        "id": coa.pk,
                        "is_approved": bool(
                            coa.is_approved
                        ),
                        "is_verified": (
                            integrity_status
                            == "VALID"
                        ),
                        "integrity_status": (
                            integrity_status
                        ),
                        "generation_status": getattr(
                            coa,
                            "generation_status",
                            None,
                        ),
                        "pdf_available": bool(
                            coa.pdf_file
                            and coa.pdf_file.name
                        ),
                        "qr_available": bool(
                            coa.qr_code
                            and coa.qr_code.name
                        ),
                    }
                    if coa
                    else None
                ),
                "results": results,
            }
        )


class ChemicalAnalysisInputDetailView(
    CaWanjalaMixin,
    DetailView,
):
    model = ChemicalAnalysisInput
    template_name = "ca/chema/analysis_input_detail.html"
    context_object_name = "analysis_input"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_object(self, queryset=None):
        queryset = _analysis_input_queryset(
            self.request.user
        )

        return get_object_or_404(
            queryset,
            pk=self.kwargs["pk"],
        )


class RecalculateAnalysisInputView(
    CaWanjalaMixin,
    View,
):
    permission_required_view = CHEMICAL_PERMISSIONS["result"]

    def post(self, request, *args, **kwargs):

        with transaction.atomic():
            analysis_input = get_object_or_404(
                _analysis_input_queryset(
                    request.user,
                    plant_id=self.get_scope_plant_id()
                )
                .select_for_update(),
                pk=kwargs["pk"],
            )

            recalculator = getattr(
                analysis_input,
                "recalculate",
                None,
            )

            if not callable(recalculator):
                calculate = getattr(
                    analysis_input,
                    "calculate",
                    None,
                )

                if not callable(calculate):
                    raise ValidationError(
                        "This analysis input does not support recalculation."
                    )

                calculate()
                analysis_input.save(
                    update_fields=[
                        "calculated_value",
                    ]
                )
            else:
                recalculator()

            analysis_input.refresh_from_db()

        messages.success(
            request,
            "Analysis input recalculated successfully.",
        )

        return redirect(
            reverse(
                "ca:analysis-input-detail",
                kwargs={
                    "pk": analysis_input.pk
                },
            )
        )


class ChemicalSpecificationListView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalSpecification
    template_name = "ca/chema/specification_list.html"
    context_object_name = "specifications"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]
    paginate_by = 50

    def get_queryset(self):
        queryset = _specification_queryset(
            self.request.user
        )

        chemical = self.request.GET.get(
            "chemical"
        )

        parameter = self.request.GET.get(
            "parameter"
        )

        if chemical:
            queryset = queryset.filter(
                chemical__name__icontains=chemical
            )

        if parameter:
            queryset = queryset.filter(
                parameter_name__icontains=parameter
            )

        return queryset


class ChemicalSpecificationFilterView(
    CaWanjalaMixin,
    View,
):
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]

    def get(self, request, *args, **kwargs):
        form = ChemicalSpecificationFilterForm(
            request.GET or None,
            user=request.user,
        )

        queryset = _specification_queryset(
            request.user
        )

        if form.is_valid():
            chemical = form.cleaned_data.get(
                "chemical"
            )

            treatment_plant = (
                form.cleaned_data.get(
                    "treatment_plant"
                )
            )

            parameter = (
                form.cleaned_data.get(
                    "parameter_name"
                )
            )

            if chemical:
                queryset = queryset.filter(
                    chemical=chemical
                )

            if treatment_plant:
                queryset = queryset.filter(
                    treatment_plant=treatment_plant
                )

            if parameter:
                queryset = queryset.filter(
                    parameter_name__icontains=parameter
                )

        return JsonResponse(
            {
                "results": [
                    {
                        "id": specification.pk,
                        "chemical": (
                            specification.chemical.name
                        ),
                        "parameter": (
                            specification.parameter_name
                        ),
                        "unit": specification.unit,
                        "minimum": (
                            str(
                                specification.minimum
                            )
                            if specification.minimum
                            is not None
                            else None
                        ),
                        "maximum": (
                            str(
                                specification.maximum
                            )
                            if specification.maximum
                            is not None
                            else None
                        ),
                        "version": (
                            specification.version
                        ),
                    }
                    for specification in queryset[:500]
                ]
            }
        )


class ResultListView(
    CaWanjalaMixin,
    ListView,
):
    model = BatchTestResult
    template_name = "ca/chema/result_list.html"
    context_object_name = "results"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]
    paginate_by = 50

    def get_queryset(self):
        queryset = _result_display_queryset(
            self.request.user
        )

        status = self.request.GET.get(
            "status"
        )

        if status:
            queryset = queryset.filter(
                status=status
            )

        query = self.request.GET.get("q")

        if query:
            queryset = queryset.filter(
                Q(
                    batch__sample_id__icontains=query
                )
                | Q(
                    parameter__parameter_name__icontains=query
                )
                | Q(
                    batch__chemical__name__icontains=query
                )
            )

        form = TestResultFilterForm(
            self.request.GET or None,
            user=self.request.user,
        )

        if form.is_valid():
            parameter = form.cleaned_data.get(
                "parameter"
            )

            if parameter:
                queryset = queryset.filter(
                    parameter=parameter
                )

        return queryset


class ResultDetailView(
    CaWanjalaMixin,
    DetailView,
):
    model = BatchTestResult
    template_name = "ca/chema/result_detail.html"
    context_object_name = "result"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_object(self, queryset=None):
        return _get_result_or_404(
            self.request.user,
            self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(
            **kwargs
        )

        context["analysis_input"] = (
            _analysis_input_queryset(
                self.request.user,
                plant_id=self.get_scope_plant_id()
            )
            .filter(
                test_result=self.object
            )
            .first()
        )

        return context


class ChemicalCoAListView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalCoA
    template_name = "ca/chema/coa_list.html"
    context_object_name = "coas"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]
    paginate_by = 50

    def get_queryset(self):
        queryset = _coa_display_queryset(
            self.request.user
        )

        query = self.request.GET.get("q")

        if query:
            queryset = queryset.filter(
                Q(
                    batch__sample_id__icontains=query
                )
                | Q(
                    batch__batch_number__icontains=query
                )
                | Q(
                    batch__chemical__name__icontains=query
                )
                | Q(
                    batch__supplier__name__icontains=query
                )
            )

        status = self.request.GET.get(
            "status"
        )

        if status == "approved":
            queryset = queryset.filter(
                is_approved=True
            )

        elif status == "pending":
            queryset = queryset.filter(
                is_approved=False
            )

        elif status == "verified":
            queryset = queryset.filter(
                verified_hash__isnull=False
            )

        elif status == "unverified":
            queryset = queryset.filter(
                Q(verified_hash__isnull=True)
                | Q(verified_hash="")
            )

        return queryset


class ChemicalCoADetailView(
    CaWanjalaMixin,
    DetailView,
):
    model = ChemicalCoA
    template_name = "ca/dashboard/pages/coa/detail.html"
    context_object_name = "coa"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_object(self, queryset=None):
        return _get_coa_or_404(
            self.request.user,
            self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(
            **kwargs
        )

        coa = self.object
        batch = getattr(
            coa,
            "batch",
            None,
        )

        process = None

        if batch is not None:
            process = (
                _process_display_queryset(
                    self.request.user,
                    plant_id=self.get_scope_plant_id()
                )
                .filter(batch=batch)
                .first()
            )

        for context_name, method_name in {
            "results": "get_results",
            "result_counts": "get_result_counts",
            "result_statistics": "get_result_statistics",
            "verification_payload": "get_verification_payload",
        }.items():
            method = getattr(
                coa,
                method_name,
                None,
            )

            if not callable(method):
                context[context_name] = None
                continue

            try:
                context[context_name] = method()
            except (
                TypeError,
                ValueError,
                ValidationError,
            ):
                context[context_name] = None

        context.update(
            {
                "process": process,
                "is_approved": bool(
                    getattr(
                        coa,
                        "is_approved",
                        False,
                    )
                ),
                "is_locked": bool(
                    getattr(
                        coa,
                        "is_locked",
                        False,
                    )
                ),
                "is_complete": bool(
                    getattr(
                        coa,
                        "is_complete",
                        False,
                    )
                ),
                "can_generate": self._safe_boolean_property(
                    coa,
                    "can_generate",
                ),
                "integrity_status": getattr(
                    coa,
                    "integrity_status",
                    None,
                ),
                "generation_status": getattr(
                    coa,
                    "generation_status",
                    None,
                ),
                "missing_assets": self._safe_collection(
                    coa,
                    "missing_assets",
                ),
                "has_failed_results": bool(
                    getattr(
                        coa,
                        "has_failed_results",
                        False,
                    )
                ),
                "has_na_results": bool(
                    getattr(
                        coa,
                        "has_na_results",
                        False,
                    )
                ),
                "has_pending_results": bool(
                    getattr(
                        coa,
                        "has_pending_results",
                        False,
                    )
                ),
                "workflow_permissions": {
                    "view": self.user_has_ca_permission(
                        CHEMICAL_PERMISSIONS["view_workflow"]
                    ),
                    "generate": self.user_has_ca_permission(
                        CHEMICAL_PERMISSIONS["generate_coa"]
                    ),
                    "approve": self.user_has_ca_permission(
                        CHEMICAL_PERMISSIONS["approve_coa"]
                    ),
                    "verify": self.user_has_ca_permission(
                        CHEMICAL_PERMISSIONS["verify_coa"]
                    ),
                },
            }
        )

        context["can_regenerate"] = (
            context["workflow_permissions"]["generate"]
            and not context["is_approved"]
            and not context["is_locked"]
        )

        context["coa_identity"] = {
            "id": coa.pk,
            "sample_id": getattr(
                coa,
                "sample_id",
                None,
            ),
            "certificate_number": (
                self._certificate_number(coa)
            ),
            "title": getattr(
                coa,
                "title",
                None,
            ),
        }

        context["traceability"] = (
            self._build_traceability(coa)
        )

        return context

    @staticmethod
    def _safe_boolean_property(
        obj,
        name,
    ):
        try:
            value = getattr(
                obj,
                name,
                False,
            )

            if callable(value):
                value = value()

            return bool(value)

        except (
            TypeError,
            ValueError,
            ValidationError,
        ):
            return False

    @staticmethod
    def _safe_collection(
        obj,
        name,
    ):
        try:
            value = getattr(
                obj,
                name,
                [],
            )

            if callable(value):
                value = value()

            if value is None:
                return []

            return list(value)

        except (
            TypeError,
            ValueError,
            ValidationError,
        ):
            return []

    @staticmethod
    def _certificate_number(coa):
        if coa.pk:
            return f"COA-{coa.pk:06d}"

        sample_id = getattr(
            coa,
            "sample_id",
            None,
        )

        if sample_id:
            return f"COA-{sample_id}"

        return "COA-DRAFT"

    @staticmethod
    def _build_traceability(coa):
        batch = getattr(
            coa,
            "batch",
            None,
        )

        chemical = getattr(
            batch,
            "chemical",
            None,
        )

        supplier = getattr(
            batch,
            "supplier",
            None,
        )

        treatment_plant = getattr(
            batch,
            "treatment_plant",
            None,
        )

        return {
            "batch_id": getattr(
                batch,
                "pk",
                None,
            ),
            "sample_id": getattr(
                batch,
                "sample_id",
                None,
            ),
            "batch_number": getattr(
                batch,
                "batch_number",
                None,
            ),
            "batch_status": getattr(
                batch,
                "status",
                None,
            ),
            "chemical": getattr(
                chemical,
                "name",
                None,
            ),
            "chemical_code": getattr(
                chemical,
                "code",
                None,
            ),
            "chemical_grade": getattr(
                chemical,
                "grade",
                None,
            ),
            "supplier": getattr(
                supplier,
                "name",
                None,
            ),
            "contract_number": getattr(
                supplier,
                "contract_number",
                None,
            ),
            "treatment_plant": treatment_plant,
        }


class RegenerateChemicalCoAView(
    CaWanjalaMixin,
    View,
):
    permission_required_view = CHEMICAL_PERMISSIONS["generate_coa"]

    def post(self, request, *args, **kwargs):

        with transaction.atomic():
            coa = _get_coa_or_404(
                request.user,
                kwargs["pk"],
                lock=True,
            )

            self._validate_regeneration(coa)

            regenerate = getattr(
                coa,
                "regenerate_content",
                None,
            )

            if not callable(regenerate):
                raise ValidationError(
                    "This Certificate of Analysis does not support regeneration."
                )

            regenerate()

            coa.save(
                populate=False,
                regenerate_watermark=False,
                regenerate_hash=False,
                generate_assets=True,
            )

            self._refresh_integrity(coa)

        if self._is_htmx(request):
            return self._htmx_success_response(
                coa
            )

        if self._is_json(request):
            return JsonResponse(
                {
                    "success": True,
                    "message": (
                        "Certificate of Analysis "
                        "regenerated successfully."
                    ),
                    "coa_id": coa.pk,
                    "redirect_url": reverse(
                        "ca:coa-detail",
                        kwargs={
                            "pk": coa.pk
                        },
                    ),
                    "integrity_status": getattr(
                        coa,
                        "integrity_status",
                        None,
                    ),
                    "generation_status": getattr(
                        coa,
                        "generation_status",
                        None,
                    ),
                }
            )

        messages.success(
            request,
            "Certificate of Analysis regenerated successfully.",
        )

        return redirect(
            reverse(
                "ca:coa-detail",
                kwargs={
                    "pk": coa.pk
                },
            )
        )

    @staticmethod
    def _validate_regeneration(coa):
        if getattr(
            coa,
            "is_approved",
            False,
        ):
            raise ValidationError(
                "An approved Certificate of Analysis cannot be regenerated."
            )

        if getattr(
            coa,
            "is_locked",
            False,
        ):
            raise ValidationError(
                "This Certificate of Analysis is locked and cannot be regenerated."
            )

        batch = getattr(
            coa,
            "batch",
            None,
        )

        if batch is None:
            raise ValidationError(
                "The Certificate of Analysis is not linked to a chemical batch."
            )

        validate = getattr(
            coa,
            "validate_generation_requirements",
            None,
        )

        if callable(validate):
            validate()

    @staticmethod
    def _refresh_integrity(coa):
        refresh_hash = getattr(
            coa,
            "refresh_hash",
            None,
        )

        if callable(refresh_hash):
            refresh_hash()

    @staticmethod
    def _is_htmx(request):
        return (
            request.headers.get(
                "HX-Request"
            )
            == "true"
        )

    @staticmethod
    def _is_json(request):
        accept = request.headers.get(
            "Accept",
            "",
        )

        return (
            "application/json" in accept
            or request.headers.get(
                "X-Requested-With"
            )
            == "XMLHttpRequest"
        )

    @staticmethod
    def _htmx_success_response(coa):
        response = JsonResponse(
            {
                "success": True,
                "message": (
                    "Certificate of Analysis "
                    "regenerated successfully."
                ),
                "coa_id": coa.pk,
            }
        )

        response["HX-Trigger"] = (
            "coa:regenerated"
        )

        return response


class VerifyChemicalCoAView(
    CaWanjalaMixin,
    View,
):
    permission_required_view = CHEMICAL_PERMISSIONS["verify_coa"]

    def post(self, request, *args, **kwargs):

        with transaction.atomic():
            coa = _get_coa_or_404(
                request.user,
                kwargs["pk"],
                lock=True,
            )

            verifier = getattr(
                coa,
                "verify_integrity",
                None,
            )

            if not callable(verifier):
                raise ValidationError(
                    "This Certificate of Analysis does not support integrity verification."
                )

            result = verifier()

            coa.refresh_from_db()

        integrity_status = getattr(
            coa,
            "integrity_status",
            None,
        )

        return JsonResponse(
            {
                "id": coa.pk,
                "verified": (
                    integrity_status
                    == "VALID"
                ),
                "integrity_status": (
                    integrity_status
                ),
                "result": result,
            }
        )


class DownloadChemicalCoAView(
    CaWanjalaMixin,
    View,
):
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]

    def get(self, request, *args, **kwargs):
        coa = _get_coa_or_404(
            request.user,
            kwargs["pk"],
        )

        pdf_file = getattr(
            coa,
            "pdf_file",
            None,
        )

        if not (
            pdf_file
            and pdf_file.name
        ):
            raise Http404(
                "The Certificate of Analysis PDF is not available."
            )

        return redirect(
            pdf_file.url
        )


class ChecklistDetailView(
    CaWanjalaMixin,
    DetailView,
):
    model = ChecklistForWaterTreatmentChemicalAnalysis
    template_name = "ca/chema/checklist_detail.html"
    context_object_name = "checklist"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]

    def get_object(self, queryset=None):
        checklist = (
            _checklist_queryset(
                self.request.user,
                plant_id=self.get_scope_plant_id()
            )
            .filter(
                pk=self.kwargs["pk"]
            )
            .first()
        )

        if checklist is None:
            raise Http404(
                "Receiving checklist not found."
            )

        return checklist


class ReopenChecklistView(
    CaWanjalaMixin,
    View,
):
    permission_required_view = CHEMICAL_PERMISSIONS[
        "reopen_checklist"
    ]

    def post(self, request, *args, **kwargs):

        with transaction.atomic():
            checklist = get_object_or_404(
                _scope_queryset(
                    ChecklistForWaterTreatmentChemicalAnalysis.objects
                    .select_for_update(),
                    request.user,
                    "chemical_analysis_request__batch__treatment_plant_id",
                ),
                pk=kwargs["pk"],
            )

            reopen = getattr(
                checklist,
                "reopen",
                None,
            )

            if not callable(reopen):
                raise ValidationError(
                    "This checklist does not support reopening."
                )

            reopen(
                performed_by=request.user
            )

        messages.success(
            request,
            "The receiving checklist has been reopened.",
        )

        return redirect(
            reverse(
                "ca:checklist-detail",
                kwargs={
                    "pk": checklist.pk
                },
            )
        )


class ProcessStatisticsView(
    CaWanjalaMixin,
    TemplateView,
):
    template_name = (
        "ca/dashboard/pages/processes/statistics.html"
    )
    permission_required_view = CHEMICAL_PERMISSIONS[
        "view_workflow"
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(
            **kwargs
        )

        user = self.request.user
        plant_id = self.get_scope_plant_id()

        processes = _process_queryset(user, plant_id=plant_id)
        batches = _batch_queryset(user, plant_id=plant_id)
        results = _result_queryset(user, plant_id=plant_id)
        requests = _request_queryset(user, plant_id=plant_id)

        process_counts = (
            processes
            .values("status")
            .annotate(total=Count("pk"))
            .order_by("status")
        )

        batch_counts = (
            batches
            .values("status")
            .annotate(total=Count("pk"))
            .order_by("status")
        )

        result_counts = (
            results
            .values("status")
            .annotate(total=Count("pk"))
            .order_by("status")
        )

        request_counts = (
            requests
            .values("status")
            .annotate(total=Count("pk"))
            .order_by("status")
        )

        context.update(
            {
                "process_counts": process_counts,
                "batch_counts": batch_counts,
                "result_counts": result_counts,
                "request_counts": request_counts,
                "total_processes": processes.count(),
                "active_processes": processes.filter(
                    status__in=PROCESS_ACTIVE_STATUSES
                ).count(),
                "analysis_processes": processes.filter(
                    status__in=PROCESS_ANALYSIS_STATUSES
                ).count(),
                "completed_processes": processes.filter(
                    status="COMPLETED"
                ).count(),
                "rejected_processes": processes.filter(
                    status="REJECTED"
                ).count(),
                "pending_requests": requests.filter(
                    status="PENDING"
                ).count(),
                "in_progress_requests": requests.filter(
                    status="IN_PROGRESS"
                ).count(),
                "completed_requests": requests.filter(
                    status="COMPLETED"
                ).count(),
                "unassigned_requests": requests.filter(
                    assigned_analysts__isnull=True
                ).distinct().count(),
                "overdue_requests": requests.filter(
                    analysis_deadline__lt=timezone.now(),
                    status__in=[
                        "PENDING",
                        "IN_PROGRESS",
                    ],
                ).count(),
            }
        )

        return context


class ProcessRefreshView(
    CaWanjalaMixin,
    View,
):
    permission_required_view = CHEMICAL_PERMISSIONS[
        "view_workflow"
    ]

    def post(self, request, *args, **kwargs):
        process = _get_process_or_404(
            request.user,
            kwargs["pk"],
        )

        process.refresh_from_db()

        analysis_request = getattr(
            process,
            "analysis_request",
            None,
        )

        assignment = (
            _request_assignment_data(
                analysis_request
            )
            if analysis_request
            else None
        )

        return JsonResponse(
            {
                "id": process.pk,
                "status": process.status,
                "is_analysis_complete": bool(
                    process.is_analysis_complete
                ),
                "has_pending_tests": bool(
                    process.has_pending_tests
                ),
                "updated_at": (
                    process.updated_at.isoformat()
                    if getattr(
                        process,
                        "updated_at",
                        None,
                    )
                    else None
                ),
                "assignment": assignment,
            }
        )


class MyChemicalTasksView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/chema/my_tasks.html"
    context_object_name = "processes"
    permission_required_view = CHEMICAL_PERMISSIONS[
        "view_workflow"
    ]
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user

        queryset = _process_display_queryset(
            user
        )

        filters = Q()

        if (
            self.is_ca_superuser(user)
            or user.has_perm(
                CHEMICAL_PERMISSIONS["result"]
            )
        ):
            filters |= Q(
                analysis_request__assigned_analysts=user
            )

        if (
            self.is_ca_superuser(user)
            or user.has_perm(
                CHEMICAL_PERMISSIONS["qa"]
            )
        ):
            filters |= Q(
                qa_officer=user
            )

        if (
            self.is_ca_superuser(user)
            or user.has_perm(
                CHEMICAL_PERMISSIONS[
                    "approve_batch"
                ]
            )
        ):
            filters |= Q(
                approver=user
            )

        if not filters:
            return queryset.none()

        return (
            queryset
            .filter(filters)
            .distinct()
            .order_by(
                "analysis_request__analysis_deadline",
                "-updated_at",
                "-pk",
            )
        )


class OverdueAnalysisView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/chema/overdue_analysis.html"
    context_object_name = "processes"
    permission_required_view = CHEMICAL_PERMISSIONS[
        "view_workflow"
    ]
    paginate_by = 50

    def get_queryset(self):
        return (
            _process_display_queryset(
                self.request.user,
                plant_id=self.get_scope_plant_id()
            )
            .filter(
                analysis_request__analysis_deadline__lt=(
                    timezone.now()
                ),
                status__in=PROCESS_ACTIVE_STATUSES,
            )
            .order_by(
                "analysis_request__analysis_deadline",
                "pk",
            )
        )


class PendingAnalysisView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/chema/pending_analysis.html"
    context_object_name = "processes"
    permission_required_view = CHEMICAL_PERMISSIONS["result"]
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user

        return (
            _process_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(
                status__in=PROCESS_ANALYSIS_STATUSES,
                analysis_request__assigned_analysts=user,
            )
            .distinct()
            .order_by(
                "analysis_request__analysis_deadline",
                "pk",
            )
        )


class PendingApprovalView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/chema/pending_approval.html"
    context_object_name = "processes"
    permission_required_view = CHEMICAL_PERMISSIONS[
        "approve_batch"
    ]
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user

        queryset = (
            _process_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(
                status="QA",
                qa_reviewed_at__isnull=False,
            )
            .filter(
                Q(
                    approver=user
                )
                | Q(
                    approver__isnull=True
                )
            )
        )

        return queryset.distinct().order_by(
            "qa_reviewed_at",
            "pk",
        )


class PendingQAReviewView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/chema/pending_qa.html"
    context_object_name = "processes"
    permission_required_view = CHEMICAL_PERMISSIONS["view_workflow"]
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        return (
            _process_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(status="QA")
            .distinct()
            .order_by("-updated_at", "-pk")
        )


class PendingCoAApprovalView(
    CaWanjalaMixin,
    ListView,
):
    model = ChemicalAnalysisProcess
    template_name = "ca/chema/pending_coa_approval.html"
    context_object_name = "processes"
    permission_required_view = CHEMICAL_PERMISSIONS["approve_coa"]
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        return (
            _process_display_queryset(user, plant_id=self.get_scope_plant_id())
            .filter(status__in=["QA", "APPROVED", "COMPLETED"])
            .distinct()
            .order_by("-updated_at", "-pk")
        )
