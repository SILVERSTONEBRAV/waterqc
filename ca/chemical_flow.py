from __future__ import annotations

import json
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from viewflow import this
from viewflow.workflow import flow, lock
from viewflow.workflow.flow import views
from viewflow.workflow.flow.views import mixins

from .forms import (
    AnalystAssignmentForm,
    AnalystAutoAssignmentForm,
    ApprovalForm,
    BatchTestResultForm,
    CAPAForm,
    ChemicalAnalysisInputForm,
    ChemicalAnalysisRequestForm,
    ChemicalBatchForm,
    ChecklistForm,
    CoAApprovalForm,
    CoAGenerationForm,
    CompleteAnalysisForm,
    CompleteChecklistForm,
    ConfirmActionForm,
    DynamicChemicalAnalysisInputForm,
    QAReviewForm,
    ReceiveChemicalBatchForm,
    RejectAnalysisForm,
    RetestForm,
    ReturnToSupplierForm,
    StartAnalysisForm,
    UtilizationForm,
)
from .models import (
    BatchTestResult,
    ChemicalAnalysisInput,
    ChemicalAnalysisProcess,
    ChemicalAnalysisRequest,
    ChemicalBatch,
    ChemicalCoA,
    ChecklistForWaterTreatmentChemicalAnalysis,
)


User = get_user_model()


class ChemicalWorkflowTaskView(
    LoginRequiredMixin,
    mixins.TaskSuccessUrlMixin,
):
    form_class = None
    template_name = "ca/workflow/task.html"
    post_methods = {"POST", "PUT", "PATCH"}

    def get_activation(self):
        activation = getattr(self.request, "activation", None)
        if activation is None:
            raise PermissionDenied("This view must be executed by Viewflow.")
        return activation

    def get_process(self):
        process = self.get_activation().process
        if process is None:
            raise PermissionDenied("No workflow process is attached to this task.")
        if not isinstance(process, ChemicalAnalysisProcess):
            process = (
                ChemicalAnalysisProcess.objects
                .select_related("batch", "analysis_request")
                .get(pk=process.pk)
            )
        return process

    def get_batch(self):
        batch = self.get_process().batch
        if batch is None:
            raise ValidationError("This workflow has no chemical batch.")
        return batch

    def get_analysis_request(self):
        request = self.get_process().analysis_request
        if request is None:
            raise ValidationError("This workflow has no analysis request.")
        return request

    def get_task_data(self) -> dict[str, Any]:
        data = self.get_activation().task.data
        return data if isinstance(data, dict) else {}

    def set_task_data(self, **values: Any):
        task = self.get_activation().task
        data = task.data if isinstance(task.data, dict) else {}
        data.update(values)
        task.data = data
        task.save(update_fields=["data"])
        return data

    def get_form_kwargs(self):
        if self.request.method in self.post_methods:
            return {
                "data": self.request.POST,
                "files": self.request.FILES,
            }
        return {}

    def get_form(self):
        if self.form_class is None:
            raise ImproperlyConfigured("form_class must be defined.")
        return self.form_class(
            user=self.request.user,
            process=self.get_process(),
            batch=self.get_batch(),
            **self.get_form_kwargs(),
        )

    def get_context_data(self, *, form, **extra):
        activation = self.get_activation()
        process = self.get_process()
        context = {
            "form": form,
            "process": process,
            "batch": process.batch,
            "analysis_request": process.analysis_request,
            "activation": activation,
            "task": activation.task,
            "flow_task": activation.flow_task,
            "workflow_status": process.status,
            "task_data": self.get_task_data(),
        }
        context.update(extra)
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data(form=self.get_form()))

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if not form.is_valid():
            return render(request, self.template_name, self.get_context_data(form=form))

        with transaction.atomic():
            process = (
                ChemicalAnalysisProcess.objects
                .select_for_update()
                .select_related("batch", "analysis_request")
                .get(pk=self.get_process().pk)
            )
            self.assert_process_scope(process)
            result = self.save_form(form)
            self.after_save(form=form, result=result)
            self.get_activation().execute()

        return redirect(self.get_success_url())

    def assert_process_scope(self, process):
        user = self.request.user
        if user.is_superuser:
            return
        plant_id = getattr(user, "assigned_treatment_plant_id", None)
        if plant_id is None:
            raise PermissionDenied("Your account is not assigned to a treatment plant.")
        if process.batch is None or process.batch.treatment_plant_id != plant_id:
            raise PermissionDenied("This workflow belongs to another treatment plant.")

    def require_permission(self, permission):
        if self.request.user.is_superuser:
            return
        if not self.request.user.has_perm(permission):
            raise PermissionDenied("You do not have permission to perform this action.")

    def require_active_user(self):
        if not self.request.user.is_active:
            raise PermissionDenied("Your account is inactive.")

    def require_status(self, *statuses):
        if self.get_process().status not in statuses:
            raise ValidationError("This workflow task is not available at the current stage.")

    def save_form(self, form):
        return form.save()

    def after_save(self, *, form, result):
        return None


class StartChemicalBatchView(LoginRequiredMixin, views.CreateArtifactView):
    model = ChemicalBatch
    form_class = ChemicalBatchForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        activation = getattr(self.request, "activation", None)
        if activation is None:
            raise PermissionDenied("This view must be executed by Viewflow.")

        with transaction.atomic():
            response = super().form_valid(form)
            process = (
                ChemicalAnalysisProcess.objects
                .select_for_update()
                .get(pk=activation.process.pk)
            )
            batch = (
                ChemicalBatch.objects
                .select_for_update()
                .get(pk=self.object.pk)
            )

            if batch.treatment_plant_id is None:
                raise ValidationError("A treatment plant is required for a chemical batch.")
            if (
                not self.request.user.is_superuser
                and batch.treatment_plant_id != getattr(
                    self.request.user, "assigned_treatment_plant_id", None
                )
            ):
                raise PermissionDenied("The chemical batch belongs to another treatment plant.")

            process.batch = batch
            process.initiated_by = self.request.user
            process.status = ChemicalAnalysisProcess.WorkflowStatus.CREATED
            process.save(update_fields=["batch", "initiated_by", "status", "updated_at"])
            return response


class ReceiveChemicalBatchTaskView(ChemicalWorkflowTaskView):
    form_class = ReceiveChemicalBatchForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(batch=self.get_batch(), process=self.get_process(), user=self.request.user)
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.receive_chemical_batch")
        self.require_status(
            ChemicalAnalysisProcess.WorkflowStatus.CREATED,
            ChemicalAnalysisProcess.WorkflowStatus.RECEIVED,
        )
        batch = self.get_batch()
        if batch.status != ChemicalBatch.Status.RECEIVED:
            raise ValidationError("The chemical batch must be in RECEIVED state.")
        remarks = (form.cleaned_data.get("remarks") or "").strip()
        if remarks:
            batch.remarks = remarks
            batch.save(update_fields=["remarks", "updated_at"])
        process = self.get_process()
        process.status = ChemicalAnalysisProcess.WorkflowStatus.RECEIVED
        process.save(update_fields=["status", "updated_at"])
        return batch


class CreateChemicalAnalysisRequestTaskView(ChemicalWorkflowTaskView):
    form_class = ChemicalAnalysisRequestForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        batch = self.get_batch()
        kwargs.update(
            user=self.request.user,
            batch=batch,
            process=self.get_process(),
            treatment_plant=batch.treatment_plant,
        )
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.create_analysis_request")
        process = self.get_process()
        batch = self.get_batch()
        if batch.status != ChemicalBatch.Status.RECEIVED:
            raise ValidationError("The chemical batch must be received before creating the analysis request.")
        if process.analysis_request_id:
            raise ValidationError("An analysis request already exists for this process.")

        form.instance.batch = batch
        form.instance.requested_by = self.request.user
        request = form.save()

        process.analysis_request = request
        process.status = ChemicalAnalysisProcess.WorkflowStatus.REQUESTED
        process.save(update_fields=["analysis_request", "status", "updated_at"])

        request.auto_assign_analysts_if_due()
        return request


class AnalystAssignmentTaskView(ChemicalWorkflowTaskView):
    form_class = AnalystAssignmentForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(process=self.get_process(), user=self.request.user)
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.create_analysis_request")
        process = self.get_process()
        request = self.get_analysis_request()
        analysts = form.cleaned_data.get("analysts")
        if request.status != ChemicalAnalysisRequest.Status.PENDING:
            raise ValidationError("Manual analyst assignment is only available while the analysis request is pending.")
        request.assign_analysts(analysts, assigned_by=self.request.user, manual=True)
        self.set_task_data(
            assignment_mode="MANUAL",
            assigned_analyst_ids=list(request.assigned_analysts.values_list("pk", flat=True)),
            assigned_at=timezone.now().isoformat(),
        )
        return request


class AnalystAutoAssignmentTaskView(ChemicalWorkflowTaskView):
    form_class = AnalystAutoAssignmentForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(process=self.get_process(), user=self.request.user)
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.create_analysis_request")
        request = self.get_analysis_request()
        if not request.assignment_overdue:
            raise ValidationError("Automatic analyst assignment is not yet due.")
        assigned = request.auto_assign_analysts_if_due()
        if not assigned.exists():
            raise ValidationError("No scheduled chemical-analysis analyst is currently available for automatic assignment.")
        self.set_task_data(
            assignment_mode="AUTOMATIC",
            assigned_analyst_ids=list(assigned.values_list("pk", flat=True)),
            assigned_at=timezone.now().isoformat(),
        )
        return request


class ChecklistTaskView(ChemicalWorkflowTaskView):
    form_class = ChecklistForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            request=self.get_analysis_request(),
            user=self.request.user,
            process=self.get_process(),
            batch=self.get_batch(),
        )
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.complete_receiving_checklist")
        self.require_status(
            ChemicalAnalysisProcess.WorkflowStatus.REQUESTED,
            ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST,
        )
        return form.save()


class CompleteChecklistTaskView(ChemicalWorkflowTaskView):
    form_class = CompleteChecklistForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            user=self.request.user,
            process=self.get_process(),
            batch=self.get_batch(),
            request=self.get_analysis_request(),
        )
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.complete_receiving_checklist")
        process = self.get_process()
        request = self.get_analysis_request()
        checklist = (
            ChecklistForWaterTreatmentChemicalAnalysis.objects
            .select_for_update()
            .filter(chemical_analysis_request=request)
            .order_by("-pk")
            .first()
        )
        if checklist is None:
            raise ValidationError("The receiving checklist must exist before completion.")
        if not checklist.completed:
            checklist.completed = True
            checklist.completed_at = timezone.now()
            checklist.completed_by = self.request.user
            checklist.save(update_fields=["completed", "completed_at", "completed_by", "updated_at"])
        process.checklist_completed_at = process.checklist_completed_at or checklist.completed_at or timezone.now()
        process.status = ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST
        process.save(update_fields=["checklist_completed_at", "status", "updated_at"])
        return process


class StartAnalysisTaskView(ChemicalWorkflowTaskView):
    form_class = StartAnalysisForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, process=self.get_process(), batch=self.get_batch())
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.start_chemical_analysis")
        process = self.get_process()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST:
            raise ValidationError("Chemical analysis can only start after the receiving checklist is complete.")
        if not process.analysis_ready:
            raise ValidationError("A completed receiving checklist is required before analysis.")
        request = self.get_analysis_request()
        if not request.has_assigned_analysts:
            request.auto_assign_analysts_if_due()
            request.refresh_from_db()
        if not request.has_assigned_analysts:
            raise ValidationError("No analyst is assigned to this analysis. Manual assignment may be made before the 30-minute automatic assignment deadline; after the deadline the system assigns the scheduled analyst automatically.")
        if not process.is_authorized_analyst(self.request.user):
            raise PermissionDenied("You are not assigned to perform this chemical analysis.")
        process.mark_analysis_started(performed_by=self.request.user)
        process.refresh_from_db()
        return process


class RecordTestResultTaskView(ChemicalWorkflowTaskView):
    form_class = BatchTestResultForm

    def get_retest_parameter_id(self):
        value = self.get_task_data().get("retest_parameter_id")
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("The retest parameter reference is invalid.") from exc

    def get_next_parameter(self):
        process = self.get_process()
        retest_parameter_id = self.get_retest_parameter_id()
        required = process.required_specifications()
        if retest_parameter_id is not None:
            parameter = required.filter(pk=retest_parameter_id).first()
            if parameter is None:
                raise ValidationError("The selected retest parameter is invalid.")
            return parameter

        completed_ids = set(
            BatchTestResult.objects
            .filter(batch=process.batch)
            .exclude(status__isnull=True)
            .exclude(status="")
            .values_list("parameter_id", flat=True)
        )
        return required.exclude(pk__in=completed_ids).order_by("pk").first()

    def get_form_kwargs(self):
        process = self.get_process()
        process.refresh_assigned_analysts()
        if not process.has_assigned_analysts:
            raise ValidationError("No active analyst is assigned to this analysis.")
        if not process.is_authorized_analyst(self.request.user):
            raise PermissionDenied("You are not assigned to perform this chemical analysis.")
        kwargs = super().get_form_kwargs()
        kwargs.update(
            process=None if process.status == ChemicalAnalysisProcess.WorkflowStatus.RETEST else process,
            batch=self.get_batch(),
            analyst=self.request.user,
            user=self.request.user,
        )
        return kwargs

    def get_form(self):
        parameter = self.get_next_parameter()
        if parameter is None:
            raise ValidationError("All required analytical parameters have been completed.")
        kwargs = self.get_form_kwargs()
        existing = (
            BatchTestResult.objects
            .filter(batch=self.get_batch(), parameter=parameter)
            .first()
        )
        form = self.form_class(instance=existing, **kwargs)
        if "parameter" in form.fields:
            form.fields["parameter"].queryset = form.fields["parameter"].queryset.filter(pk=parameter.pk)
            form.initial["parameter"] = parameter.pk
        return form

    def save_form(self, form):
        self.require_permission("ca.record_chemical_result")
        process = self.get_process()
        process.refresh_assigned_analysts()
        if not process.is_authorized_analyst(self.request.user):
            raise PermissionDenied("You are not assigned to perform this chemical analysis.")
        expected = self.get_next_parameter()
        parameter = form.cleaned_data.get("parameter")
        if parameter is None or expected is None or parameter.pk != expected.pk:
            raise ValidationError("The selected parameter is not currently required.")
        result = form.save()
        if result.batch_id != process.batch_id or result.parameter_id != parameter.pk:
            raise ValidationError("The recorded result does not match this analysis.")
        self.set_task_data(
            result_id=result.pk,
            parameter_id=result.parameter_id,
            result_status=result.status,
            result_recorded_at=timezone.now().isoformat(),
        )
        return result


class RecordDynamicAnalysisInputTaskView(ChemicalWorkflowTaskView):
    form_class = DynamicChemicalAnalysisInputForm

    def get_result_id(self):
        value = self.get_task_data().get("result_id")
        if value in (None, ""):
            raise ValidationError("No analytical result is attached to this task.")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("The analytical result reference is invalid.") from exc

    def get_test_result(self):
        process = self.get_process()
        process.refresh_assigned_analysts()
        if not process.is_authorized_analyst(self.request.user):
            raise PermissionDenied("You are not assigned to perform this chemical analysis.")
        result = (
            BatchTestResult.objects
            .select_related("parameter", "parameter__method")
            .filter(pk=self.get_result_id(), batch=process.batch)
            .first()
        )
        if result is None:
            raise ValidationError("The analytical test result could not be found.")
        if result.analyst_id != self.request.user.pk:
            raise PermissionDenied("You did not create this analytical result.")
        if result.parameter is None or result.parameter.method is None:
            raise ValidationError("The analytical result must have an analysis parameter and method.")
        fields = result.parameter.method.get_input_fields()
        if isinstance(fields, str):
            fields = [value.strip() for value in fields.split(",") if value.strip()]
        if not fields:
            raise ValidationError("This analytical method does not require method inputs.")
        return result

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            test_result=self.get_test_result(),
            user=self.request.user,
            process=self.get_process(),
            batch=self.get_batch(),
        )
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.record_chemical_result")
        test_result = self.get_test_result()
        inputs = form.as_input_dictionary()
        model_form = ChemicalAnalysisInputForm(
            data={"test_result": test_result.pk, "inputs": json.dumps(inputs)},
            test_result=test_result,
            process=self.get_process(),
            user=self.request.user,
        )
        if not model_form.is_valid():
            raise ValidationError(model_form.errors.as_json())
        result = model_form.save()
        self.set_task_data(input_record_id=result.pk, input_recorded=True, input_recorded_at=timezone.now().isoformat())
        return result


class CompleteAnalysisTaskView(ChemicalWorkflowTaskView):
    form_class = CompleteAnalysisForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, process=self.get_process(), batch=self.get_batch())
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.complete_chemical_analysis")
        process = self.get_process()
        process.refresh_assigned_analysts()
        if not process.is_authorized_analyst(self.request.user):
            raise PermissionDenied("You are not assigned to perform this chemical analysis.")
        if process.has_pending_tests or not process.is_analysis_complete:
            raise ValidationError("All required analytical results must be finalized before completing the analysis.")
        process.mark_analysis_completed(performed_by=self.request.user)
        process.refresh_from_db()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.QA:
            raise ValidationError("Chemical analysis did not advance to QA.")
        return process


class RetestTaskView(ChemicalWorkflowTaskView):
    form_class = RetestForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(process=self.get_process(), batch=self.get_batch(), user=self.request.user)
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.perform_chemical_retest")
        process = self.get_process()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.QA:
            raise ValidationError("Retesting can only be requested during QA.")
        process.refresh_assigned_analysts()
        if not process.is_authorized_analyst(self.request.user):
            raise PermissionDenied("You are not assigned to this chemical analysis.")
        parameter = form.cleaned_data.get("parameter")
        reason = (form.cleaned_data.get("reason") or "").strip()
        if parameter is None or not reason:
            raise ValidationError("A retest parameter and reason are required.")
        if not process.required_specifications().filter(pk=parameter.pk).exists():
            raise ValidationError("The selected parameter is not required for this analysis.")
        process.rework_count += 1
        process.status = ChemicalAnalysisProcess.WorkflowStatus.RETEST
        process.save(update_fields=["rework_count", "status", "updated_at"])
        self.set_task_data(
            retest_parameter_id=parameter.pk,
            retest_reason=reason,
            retest_requested_by_id=self.request.user.pk,
            retest_requested_at=timezone.now().isoformat(),
        )
        return parameter


class CompleteRetestTaskView(ChemicalWorkflowTaskView):
    form_class = ConfirmActionForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, process=self.get_process(), batch=self.get_batch())
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.perform_chemical_retest")
        process = self.get_process()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.RETEST:
            raise ValidationError("The analysis is not currently in the retest stage.")
        parameter_id = self.get_task_data().get("retest_parameter_id")
        if not parameter_id:
            raise ValidationError("No retest parameter is attached to this retest.")
        try:
            parameter_id = int(parameter_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError("The retest parameter reference is invalid.") from exc
        result = (
            BatchTestResult.objects
            .filter(batch=process.batch, parameter_id=parameter_id)
            .first()
        )
        if result is None or not result.status:
            raise ValidationError("The required retest result has not been finalized.")
        process.status = ChemicalAnalysisProcess.WorkflowStatus.QA
        process.save(update_fields=["status", "updated_at"])
        self.set_task_data(retest_completed=True, retest_result_id=result.pk, retest_completed_at=timezone.now().isoformat())
        return process


class QAReviewTaskView(ChemicalWorkflowTaskView):
    form_class = QAReviewForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, process=self.get_process(), batch=self.get_batch())
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.review_chemical_analysis")
        process = self.get_process()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.QA:
            raise ValidationError("The analysis must be in QA before review.")
        if process.has_pending_tests or not process.is_analysis_complete:
            raise ValidationError("All required analytical results must be finalized before QA review.")
        decision = str(form.cleaned_data.get("decision", "")).upper()
        remarks = (form.cleaned_data.get("remarks") or "").strip()
        if decision not in {"PASS", "REWORK", "CAPA", "REJECT"}:
            raise ValidationError("Invalid QA decision.")
        if decision == "PASS" and process.failed_tests.exists():
            raise ValidationError("A failed analysis cannot pass QA.")
        process.qa_officer = self.request.user
        process.qa_reviewed_at = timezone.now()
        process.save(update_fields=["qa_officer", "qa_reviewed_at", "updated_at"])
        self.set_task_data(
            decision=decision,
            remarks=remarks,
            reviewed_by_id=self.request.user.pk,
            reviewed_at=timezone.now().isoformat(),
        )
        return process


class CAPATaskView(ChemicalWorkflowTaskView):
    form_class = CAPAForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, process=self.get_process())
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.review_chemical_analysis")
        process = self.get_process()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.QA:
            raise ValidationError("CAPA can only be initiated during QA.")
        self.set_task_data(
            capa_submitted=True,
            corrective_action=(form.cleaned_data.get("corrective_action") or "").strip(),
            preventive_action=(form.cleaned_data.get("preventive_action") or "").strip(),
            capa_submitted_by_id=self.request.user.pk,
            capa_submitted_at=timezone.now().isoformat(),
        )
        return process


class ApprovalTaskView(ChemicalWorkflowTaskView):
    form_class = ApprovalForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, process=self.get_process(), batch=self.get_batch())
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.approve_chemical_batch")
        process = self.get_process()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.QA:
            raise ValidationError("Chemical analysis approval is only available after QA review.")
        if process.has_pending_tests or process.failed_tests.exists() or not process.is_analysis_complete:
            raise ValidationError("The analysis must be complete with no failed results before approval.")
        if str(form.cleaned_data.get("decision", "APPROVE")).upper() != "APPROVE":
            raise ValidationError("Only APPROVE is valid at this stage.")
        process.mark_approved(approved_by=self.request.user)
        process.refresh_from_db()
        return process


class GenerateChemicalCoATaskView(ChemicalWorkflowTaskView):
    form_class = CoAGenerationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, process=self.get_process(), batch=self.get_batch())
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.approve_chemical_coa")
        process = self.get_process()
        batch = self.get_batch()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.APPROVED:
            raise ValidationError("The CoA can only be generated after chemical analysis approval.")
        if batch.status != ChemicalBatch.Status.APPROVED:
            raise ValidationError("The chemical batch must be approved before CoA generation.")
        coa, _ = ChemicalCoA.objects.select_for_update().get_or_create(batch=batch)
        if not (coa.pdf_file and coa.qr_code):
            coa.prepare_for_generation()
            coa.save(generate_assets=True, regenerate_watermark=True)
            coa.refresh_from_db()
        if not coa.pdf_file or not coa.qr_code:
            raise ValidationError("The CoA assets could not be generated completely.")
        batch.coa_generated = True
        batch.save(update_fields=["coa_generated", "updated_at"])
        self.set_task_data(coa_id=coa.pk, coa_generated=True, coa_approved=coa.is_approved)
        return coa


class ApproveChemicalCoATaskView(ChemicalWorkflowTaskView):
    form_class = CoAApprovalForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, process=self.get_process(), batch=self.get_batch())
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.approve_chemical_coa")
        process = self.get_process()
        batch = self.get_batch()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.APPROVED:
            raise ValidationError("CoA approval is only available after chemical analysis approval.")
        coa = ChemicalCoA.objects.select_for_update().filter(batch=batch).first()
        if coa is None:
            raise ValidationError("The Certificate of Analysis has not been generated.")
        if not coa.pdf_file or not coa.qr_code:
            raise ValidationError("The Certificate of Analysis is incomplete.")
        if not coa.is_approved:
            coa.approve(approved_by=self.request.user)
            coa.refresh_from_db()
        if not coa.is_approved:
            raise ValidationError("The Certificate of Analysis was not approved.")
        self.set_task_data(coa_id=coa.pk, coa_approved=True, coa_approved_by_id=coa.approved_by_id)
        return coa


class RejectAnalysisTaskView(ChemicalWorkflowTaskView):
    form_class = RejectAnalysisForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, process=self.get_process(), batch=self.get_batch())
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.reject_chemical_batch")
        process = self.get_process()
        if process.status not in {
            ChemicalAnalysisProcess.WorkflowStatus.ANALYSIS,
            ChemicalAnalysisProcess.WorkflowStatus.RETEST,
            ChemicalAnalysisProcess.WorkflowStatus.QA,
        }:
            raise ValidationError("The analysis cannot be rejected at this workflow stage.")
        reason = (form.cleaned_data.get("reason") or form.cleaned_data.get("remarks") or "").strip()
        if not reason:
            raise ValidationError("A rejection reason is required.")
        process.mark_rejected()
        self.set_task_data(decision="REJECT", rejection_reason=reason, rejected_by_id=self.request.user.pk, rejected_at=timezone.now().isoformat())
        return process


class ConfirmWorkflowActionTaskView(ChemicalWorkflowTaskView):
    form_class = ConfirmActionForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, batch=self.get_batch(), process=self.get_process())
        return kwargs

    def save_form(self, form):
        process = self.get_process()
        batch = self.get_batch()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.APPROVED:
            raise ValidationError("Batch disposition requires an approved analysis.")
        coa = ChemicalCoA.objects.filter(batch=batch).first()
        if coa is None or not coa.is_approved:
            raise ValidationError("An approved Certificate of Analysis is required before disposition.")
        action = str(form.cleaned_data.get("action", "")).upper()
        if action not in {"UTILIZE", "RETURN"}:
            raise ValidationError("Invalid batch disposition.")
        self.require_permission({"UTILIZE": "ca.utilize_chemical_batch", "RETURN": "ca.return_chemical_batch"}[action])
        self.set_task_data(action=action, disposition_selected_by_id=self.request.user.pk, disposition_selected_at=timezone.now().isoformat())
        return action


class UtilizeChemicalBatchTaskView(ChemicalWorkflowTaskView):
    form_class = UtilizationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(batch=self.get_batch(), process=self.get_process(), user=self.request.user)
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.utilize_chemical_batch")
        process = self.get_process()
        batch = self.get_batch()
        if process.status != ChemicalAnalysisProcess.WorkflowStatus.APPROVED or batch.status != ChemicalBatch.Status.APPROVED:
            raise ValidationError("Only an approved chemical batch can be utilized.")
        coa = ChemicalCoA.objects.filter(batch=batch).first()
        if coa is None or not coa.is_approved:
            raise ValidationError("An approved Certificate of Analysis is required.")
        result = form.save()
        batch.transition_to(ChemicalBatch.Status.UTILIZED, performed_by=self.request.user)
        process.mark_disposition_completed(ChemicalAnalysisProcess.WorkflowStatus.UTILIZED)
        process.mark_completed()
        self.set_task_data(disposition="UTILIZED", completed_by_id=self.request.user.pk, completed_at=timezone.now().isoformat())
        return result


class ReturnChemicalBatchTaskView(ChemicalWorkflowTaskView):
    form_class = ReturnToSupplierForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(batch=self.get_batch(), process=self.get_process(), user=self.request.user)
        return kwargs

    def save_form(self, form):
        self.require_permission("ca.return_chemical_batch")
        process = self.get_process()
        batch = self.get_batch()
        if batch.status not in {ChemicalBatch.Status.APPROVED, ChemicalBatch.Status.REJECTED}:
            raise ValidationError("The chemical batch cannot currently be returned.")
        result = form.save()
        if batch.status == ChemicalBatch.Status.APPROVED:
            batch.transition_to(ChemicalBatch.Status.RETURNED, performed_by=self.request.user)
        else:
            batch.status = ChemicalBatch.Status.RETURNED
            batch.save(update_fields=["status", "updated_at"])
        process.mark_disposition_completed(ChemicalAnalysisProcess.WorkflowStatus.RETURNED)
        process.mark_completed()
        self.set_task_data(disposition="RETURNED", completed_by_id=self.request.user.pk, completed_at=timezone.now().isoformat())
        return result


class ChemicalAnalysisFlow(flow.Flow):
    process_class = ChemicalAnalysisProcess
    lock_impl = lock.select_for_update_lock

    start = (
        flow.Start(StartChemicalBatchView)
        .Annotation(title="Register Chemical Batch")
        .Permission("ca.receive_chemical_batch")
        .Next(this.receive)
    )

    receive = (
        flow.View(ReceiveChemicalBatchTaskView)
        .Annotation(title="Confirm Chemical Receipt")
        .Permission("ca.receive_chemical_batch")
        .Next(this.create_request)
    )

    create_request = (
        flow.View(CreateChemicalAnalysisRequestTaskView)
        .Annotation(title="Create Chemical Analysis Request")
        .Permission("ca.create_analysis_request")
        .Next(this.checklist)
    )

    checklist = (
        flow.View(ChecklistTaskView)
        .Annotation(title="Receiving Checklist")
        .Permission("ca.complete_receiving_checklist")
        .Next(this.complete_checklist)
    )

    complete_checklist = (
        flow.View(CompleteChecklistTaskView)
        .Annotation(title="Complete Receiving Checklist")
        .Permission("ca.complete_receiving_checklist")
        .Next(this.start_analysis)
    )

    start_analysis = (
        flow.View(StartAnalysisTaskView)
        .Annotation(title="Start Chemical Analysis")
        .Permission("ca.start_chemical_analysis")
        .Next(this.record_result)
    )

    record_result = (
        flow.View(RecordTestResultTaskView)
        .Annotation(title="Record Chemical Test Result")
        .Permission("ca.record_chemical_result")
        .Next(this.check_result_input, task_data=lambda activation: ChemicalAnalysisFlow.result_task_data(activation))
    )

    check_result_input = (
        flow.If(lambda activation: ChemicalAnalysisFlow.result_requires_input(activation))
        .Then(this.record_input)
        .Else(this.check_analysis_progress)
    )

    record_input = (
        flow.View(RecordDynamicAnalysisInputTaskView)
        .Annotation(title="Record Analytical Method Inputs")
        .Permission("ca.record_chemical_result")
        .Next(this.check_analysis_progress)
    )

    check_analysis_progress = (
        flow.If(lambda activation: ChemicalAnalysisFlow.analysis_complete(activation))
        .Then(this.complete_analysis)
        .Else(this.record_result)
    )

    complete_analysis = (
        flow.View(CompleteAnalysisTaskView)
        .Annotation(title="Complete Chemical Analysis")
        .Permission("ca.complete_chemical_analysis")
        .Next(this.qa_review)
    )

    qa_review = (
        flow.View(QAReviewTaskView)
        .Annotation(title="QA Review")
        .Permission("ca.review_chemical_analysis")
        .Next(this.qa_decision, task_data=lambda activation: ChemicalAnalysisFlow.qa_task_data(activation))
    )

    qa_decision = (
        flow.If(lambda activation: ChemicalAnalysisFlow.qa_is_retest(activation))
        .Then(this.retest)
        .Else(
            flow.If(lambda activation: ChemicalAnalysisFlow.qa_is_capa(activation))
            .Then(this.capa)
            .Else(
                flow.If(lambda activation: ChemicalAnalysisFlow.qa_is_rejected(activation))
                .Then(this.reject)
                .Else(this.approval)
            )
        )
    )

    retest = (
        flow.View(RetestTaskView)
        .Annotation(title="Request Chemical Retest")
        .Permission("ca.perform_chemical_retest")
        .Next(this.retest_result)
    )

    retest_result = (
        flow.View(RecordTestResultTaskView)
        .Annotation(title="Record Retest Result")
        .Permission("ca.record_chemical_result")
        .Next(this.check_retest_input, task_data=lambda activation: ChemicalAnalysisFlow.result_task_data(activation))
    )

    check_retest_input = (
        flow.If(lambda activation: ChemicalAnalysisFlow.result_requires_input(activation))
        .Then(this.retest_input)
        .Else(this.complete_retest)
    )

    retest_input = (
        flow.View(RecordDynamicAnalysisInputTaskView)
        .Annotation(title="Record Retest Method Inputs")
        .Permission("ca.record_chemical_result")
        .Next(this.complete_retest)
    )

    complete_retest = (
        flow.View(CompleteRetestTaskView)
        .Annotation(title="Complete Chemical Retest")
        .Permission("ca.perform_chemical_retest")
        .Next(this.qa_review)
    )

    capa = (
        flow.View(CAPATaskView)
        .Annotation(title="Corrective and Preventive Action")
        .Permission("ca.review_chemical_analysis")
        .Next(this.qa_review)
    )

    approval = (
        flow.View(ApprovalTaskView)
        .Annotation(title="Approve Chemical Analysis")
        .Permission("ca.approve_chemical_batch")
        .Next(this.generate_coa)
    )

    generate_coa = (
        flow.View(GenerateChemicalCoATaskView)
        .Annotation(title="Generate Chemical CoA")
        .Permission("ca.approve_chemical_coa")
        .Next(this.approve_coa)
    )

    approve_coa = (
        flow.View(ApproveChemicalCoATaskView)
        .Annotation(title="Approve Chemical CoA")
        .Permission("ca.approve_chemical_coa")
        .Next(this.batch_disposition)
    )

    batch_disposition = (
        flow.View(ConfirmWorkflowActionTaskView)
        .Annotation(title="Select Chemical Batch Disposition")
        .Next(this.disposition_decision, task_data=lambda activation: {"action": ChemicalAnalysisFlow.task_value(activation, "action")})
    )

    disposition_decision = (
        flow.If(lambda activation: ChemicalAnalysisFlow.disposition_is_utilize(activation))
        .Then(this.utilize)
        .Else(this.return_to_supplier)
    )

    utilize = (
        flow.View(UtilizeChemicalBatchTaskView)
        .Annotation(title="Utilize Chemical Batch")
        .Permission("ca.utilize_chemical_batch")
        .Next(this.completed)
    )

    return_to_supplier = (
        flow.View(ReturnChemicalBatchTaskView)
        .Annotation(title="Return Chemical Batch")
        .Permission("ca.return_chemical_batch")
        .Next(this.completed)
    )

    reject = (
        flow.View(RejectAnalysisTaskView)
        .Annotation(title="Reject Chemical Batch")
        .Permission("ca.reject_chemical_batch")
        .Next(this.rejected)
    )

    rejected = flow.End().Annotation(title="Chemical Analysis Rejected")
    completed = flow.End().Annotation(title="Chemical Analysis Completed")

    @staticmethod
    def task_value(activation, key, default=None):
        data = activation.task.data
        return data.get(key, default) if isinstance(data, dict) else default

    @staticmethod
    def result_task_data(activation):
        data = activation.task.data
        if not isinstance(data, dict):
            return {}
        return {
            "result_id": data.get("result_id"),
            "parameter_id": data.get("parameter_id"),
            "result_status": data.get("result_status"),
            "retest_parameter_id": data.get("retest_parameter_id"),
        }

    @staticmethod
    def qa_task_data(activation):
        data = activation.task.data
        if not isinstance(data, dict):
            return {}
        return {
            "decision": data.get("decision"),
            "remarks": data.get("remarks"),
            "reviewed_by_id": data.get("reviewed_by_id"),
            "reviewed_at": data.get("reviewed_at"),
        }

    @staticmethod
    def result_requires_input(activation):
        result_id = ChemicalAnalysisFlow.task_value(activation, "result_id")
        if result_id in (None, ""):
            return False
        try:
            result_id = int(result_id)
        except (TypeError, ValueError):
            return False
        result = (
            BatchTestResult.objects
            .select_related("parameter", "parameter__method")
            .filter(pk=result_id, batch=activation.process.batch)
            .first()
        )
        if result is None or result.parameter is None or result.parameter.method is None:
            return False
        fields = result.parameter.method.get_input_fields()
        if isinstance(fields, str):
            fields = [value.strip() for value in fields.split(",") if value.strip()]
        return bool(fields)

    @staticmethod
    def analysis_complete(activation):
        process = activation.process
        process.refresh_from_db()
        return bool(process.is_analysis_complete and not process.has_pending_tests)

    @staticmethod
    def qa_is_retest(activation):
        return str(ChemicalAnalysisFlow.task_value(activation, "decision", "")).upper() in {"RETEST", "REWORK"}

    @staticmethod
    def qa_is_capa(activation):
        return str(ChemicalAnalysisFlow.task_value(activation, "decision", "")).upper() == "CAPA"

    @staticmethod
    def qa_is_rejected(activation):
        return str(ChemicalAnalysisFlow.task_value(activation, "decision", "")).upper() == "REJECT"

    @staticmethod
    def disposition_is_utilize(activation):
        return str(ChemicalAnalysisFlow.task_value(activation, "action", "")).upper() == "UTILIZE"
