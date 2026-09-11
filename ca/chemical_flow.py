from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import (
    ImproperlyConfigured,
    PermissionDenied,
    ValidationError,
)
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View as DjangoView

from viewflow import this
from viewflow.workflow import flow, lock
from viewflow.workflow.flow import views
from viewflow.workflow.flow.views import mixins

from .forms import (
    ApprovalForm,
    BatchTestResultForm,
    ChemicalAnalysisInputForm,
    ChemicalAnalysisRequestForm,
    ChemicalBatchForm,
    ChecklistForm,
    CompleteAnalysisForm,
    CompleteChecklistForm,
    ConfirmActionForm,
    DynamicChemicalAnalysisInputForm,
    QAReviewForm,
    ReceiveChemicalBatchForm,
    RejectAnalysisForm,
    RetestForm,
    ReturnToSupplierForm,
    SamplingCounterCheckForm,
    SamplingQAApprovalForm,
    StartAnalysisForm,
    SystematicSamplingMeasurementForm,
    SystematicSamplingPlanForm,
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
    SystematicRandomSampling,
)


class ChemicalWorkflowTaskView(
    LoginRequiredMixin,
    mixins.TaskSuccessUrlMixin,
    DjangoView,
):
    form_class = None
    template_name = "ca/workflow/task.html"

    def get_activation(self):
        activation = getattr(
            self.request,
            "activation",
            None,
        )

        if activation is None:
            raise PermissionDenied(
                "This view must be executed by Viewflow."
            )

        return activation

    def get_process(self):
        process = self.get_activation().process

        if process is None:
            raise PermissionDenied(
                "No workflow process is attached to this task."
            )

        return process

    def get_batch(self):
        process = self.get_process()

        batch = getattr(
            process,
            "batch",
            None,
        )

        if batch is None:
            raise ValidationError(
                "This workflow has no chemical batch."
            )

        return batch

    def get_analysis_request(self):
        process = self.get_process()

        analysis_request = getattr(
            process,
            "analysis_request",
            None,
        )

        if analysis_request is None:
            raise ValidationError(
                "This workflow has no analysis request."
            )

        return analysis_request

    def get_sampling(self):
        process = self.get_process()

        sampling = getattr(
            process,
            "systematic_random_sampling",
            None,
        )

        if sampling is None:
            sampling = (
                SystematicRandomSampling.objects
                .filter(process=process)
                .first()
            )

        if sampling is None:
            raise ValidationError(
                "No systematic random sampling record exists for this analysis."
            )

        return sampling

    def get_task_data(self) -> dict[str, Any]:
        task = self.get_activation().task
        data = task.data

        if isinstance(data, dict):
            return data

        return {}

    def set_task_data(self, **values: Any) -> dict[str, Any]:
        activation = self.get_activation()
        task = activation.task

        data = task.data

        if not isinstance(data, dict):
            data = {}

        data.update(values)
        task.data = data
        task.save(
            update_fields=["data"]
        )

        return data

    def get_form_kwargs(self):
        kwargs: dict[str, Any] = {}

        if self.request.method in {
            "POST",
            "PUT",
            "PATCH",
        }:
            kwargs["data"] = self.request.POST
            kwargs["files"] = self.request.FILES

        return kwargs

    def get_form(self):
        if self.form_class is None:
            raise ImproperlyConfigured(
                "form_class must be defined."
            )

        return self.form_class(
            **self.get_form_kwargs()
        )

    def get_context_data(
        self,
        *,
        form,
        **extra,
    ):
        activation = self.get_activation()
        process = self.get_process()

        context = {
            "form": form,
            "process": process,
            "batch": getattr(
                process,
                "batch",
                None,
            ),
            "analysis_request": getattr(
                process,
                "analysis_request",
                None,
            ),
            "activation": activation,
            "task": activation.task,
            "flow_task": activation.flow_task,
        }

        context.update(extra)

        return context

    def get(
        self,
        request,
        *args,
        **kwargs,
    ):
        return render(
            request,
            self.template_name,
            self.get_context_data(
                form=self.get_form()
            ),
        )

    def post(
        self,
        request,
        *args,
        **kwargs,
    ):
        form = self.get_form()

        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self.get_context_data(
                    form=form
                ),
            )

        with transaction.atomic():
            result = self.save_form(form)

            self.after_save(
                form=form,
                result=result,
            )

            request.activation.execute()

        return redirect(
            self.get_success_url()
        )

    def save_form(self, form):
        if hasattr(form, "save"):
            return form.save()

        return form.cleaned_data

    def after_save(
        self,
        *,
        form,
        result,
    ):
        return None


class StartChemicalBatchView(
    LoginRequiredMixin,
    views.CreateArtifactView,
):
    model = ChemicalBatch
    form_class = ChemicalBatchForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)

            activation = getattr(
                self.request,
                "activation",
                None,
            )

            if activation is None:
                raise PermissionDenied(
                    "This view must be executed by Viewflow."
                )

            process = activation.process

            process.batch = self.object
            process.initiated_by = self.request.user
            process.status = (
                ChemicalAnalysisProcess.WorkflowStatus.CREATED
            )

            process.save(
                update_fields=[
                    "batch",
                    "initiated_by",
                    "status",
                ]
            )

            return response


class ReceiveChemicalBatchTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = ReceiveChemicalBatchForm

    def save_form(self, form):
        process = self.get_process()
        batch = self.get_batch()

        if batch.status not in {
            ChemicalBatch.Status.RECEIVED,
            ChemicalBatch.Status.CREATED,
        }:
            raise ValidationError(
                "This chemical batch cannot be received at its current status."
            )

        update_fields = []

        if batch.status != ChemicalBatch.Status.RECEIVED:
            batch.status = ChemicalBatch.Status.RECEIVED
            update_fields.append("status")

        remarks = (
            form.cleaned_data.get("remarks") or ""
        ).strip()

        if remarks and hasattr(batch, "remarks"):
            batch.remarks = remarks
            update_fields.append("remarks")

        if update_fields:
            batch.save(
                update_fields=update_fields
            )

        process.status = (
            ChemicalAnalysisProcess.WorkflowStatus.RECEIVED
        )

        process.save(
            update_fields=["status"]
        )

        return batch


class CreateChemicalAnalysisRequestTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = ChemicalAnalysisRequestForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        process = self.get_process()

        batch = getattr(
            process,
            "batch",
            None,
        )

        kwargs.update(
            {
                "user": self.request.user,
                "batch": batch,
                "treatment_plant": (
                    batch.treatment_plant
                    if batch is not None
                    else None
                ),
            }
        )

        return kwargs

    def save_form(self, form):
        process = self.get_process()

        batch = process.batch

        if batch is None:
            raise ValidationError(
                "A chemical batch is required before creating the analysis request."
            )

        if batch.status != ChemicalBatch.Status.RECEIVED:
            raise ValidationError(
                "The chemical batch must be received before creating the analysis request."
            )

        form.instance.batch = batch

        analysis_request = form.save()

        analysis_request.populate_assigned_analysts()
        analysis_request.refresh_from_db()

        if not analysis_request.assigned_analysts.filter(
            is_active=True
        ).exists():
            raise ValidationError(
                "No active analyst is currently assigned to the Water Treatment Chemical Analysis duty."
            )

        if not analysis_request.is_assigned_analyst(
            self.request.user
        ):
            process.refresh_assigned_analysts()

        process.analysis_request = analysis_request
        process.status = (
            ChemicalAnalysisProcess.WorkflowStatus.REQUESTED
        )

        process.save(
            update_fields=[
                "analysis_request",
                "status",
            ]
        )

        return analysis_request


class ChecklistTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = ChecklistForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs.update(
            {
                "request": self.get_analysis_request(),
                "user": self.request.user,
            }
        )

        return kwargs

    def save_form(self, form):
        process = self.get_process()

        checklist = form.save()

        process.status = (
            ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST
        )

        process.save(
            update_fields=["status"]
        )

        return checklist


class CompleteChecklistTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = CompleteChecklistForm

    def save_form(self, form):
        process = self.get_process()

        if process.analysis_request is None:
            raise ValidationError(
                "An analysis request is required before completing the receiving checklist."
            )

        checklist_exists = (
            ChecklistForWaterTreatmentChemicalAnalysis.objects
            .filter(
                chemical_analysis_request=process.analysis_request
            )
            .exists()
        )

        if not checklist_exists:
            raise ValidationError(
                "The chemical receiving checklist must be completed before confirmation."
            )

        process.checklist_completed_at = timezone.now()
        process.status = (
            ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST
        )

        process.save(
            update_fields=[
                "checklist_completed_at",
                "status",
            ]
        )

        return process


class StartSystematicSamplingTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = SystematicSamplingPlanForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs.update(
            {
                "process": self.get_process(),
                "batch": self.get_batch(),
                "user": self.request.user,
            }
        )

        return kwargs

    def save_form(self, form):
        process = self.get_process()
        batch = self.get_batch()

        if process.status != (
            ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST
        ):
            raise ValidationError(
                "The receiving checklist must be completed before systematic random sampling."
            )

        if not process.checklist_completed_at:
            raise ValidationError(
                "The receiving checklist has not been completed."
            )

        if process.analysis_request is None:
            raise ValidationError(
                "An analysis request is required before sampling."
            )

        process.refresh_assigned_analysts()

        if not process.has_assigned_analysts:
            raise ValidationError(
                "No active analyst is currently assigned to this chemical analysis duty."
            )

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis duty."
            )

        process.move_to_systematic_random_sampling()

        sampling, _ = (
            SystematicRandomSampling.objects
            .select_for_update()
            .get_or_create(
                process=process,
                defaults={
                    "batch": batch,
                },
            )
        )

        sampling.batch = batch

        cleaned = form.cleaned_data

        for field_name in (
            "sample_count",
            "sampling_interval",
            "random_start",
        ):
            if (
                field_name in cleaned
                and hasattr(
                    sampling,
                    field_name,
                )
            ):
                setattr(
                    sampling,
                    field_name,
                    cleaned[field_name],
                )

        sampling.save()

        generate_plan = getattr(
            sampling,
            "generate_sampling_plan",
            None,
        )

        if callable(generate_plan):
            generate_plan()

        create_samples = getattr(
            sampling,
            "create_samples",
            None,
        )

        if callable(create_samples):
            create_samples()

        process.status = (
            ChemicalAnalysisProcess.WorkflowStatus.SYSTEMATIC_RANDOM_SAMPLING
        )

        process.save(
            update_fields=["status"]
        )

        return sampling


class SystematicSamplingMeasurementTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = SystematicSamplingMeasurementForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs.update(
            {
                "sampling": self.get_sampling(),
                "user": self.request.user,
            }
        )

        return kwargs

    def save_form(self, form):
        process = self.get_process()

        process.refresh_assigned_analysts()

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis duty."
            )

        sampling = self.get_sampling()

        if getattr(
            sampling,
            "status",
            None,
        ) != "PENDING":
            raise ValidationError(
                "Sampling measurements cannot be recorded at this stage."
            )

        result = form.save()

        calculate_results = getattr(
            sampling,
            "calculate_results",
            None,
        )

        if callable(calculate_results):
            calculate_results()

        sampling.save()

        return result


class CounterCheckSystematicSamplingTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = SamplingCounterCheckForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs.update(
            {
                "sampling": self.get_sampling(),
                "user": self.request.user,
            }
        )

        return kwargs

    def save_form(self, form):
        process = self.get_process()

        process.refresh_assigned_analysts()

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis duty."
            )

        sampling = self.get_sampling()

        if getattr(
            sampling,
            "status",
            None,
        ) != "COUNTER_CHECK":
            raise ValidationError(
                "The sampling record is not ready for counter-check."
            )

        result = form.save()

        counter_check = getattr(
            sampling,
            "counter_check",
            None,
        )

        if callable(counter_check):
            counter_check(
                user=self.request.user
            )
        else:
            sampling.counter_checked_by = (
                self.request.user
            )

            if hasattr(
                sampling,
                "counter_checked_at",
            ):
                sampling.counter_checked_at = (
                    timezone.now()
                )

            sampling.status = (
                "QA_REVIEW"
                if getattr(
                    sampling,
                    "qa_required",
                    False,
                )
                else "COMPLETED"
            )

            sampling.save()

        return result


class SamplingQAApprovalTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = SamplingQAApprovalForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs.update(
            {
                "sampling": self.get_sampling(),
                "user": self.request.user,
            }
        )

        return kwargs

    def save_form(self, form):
        sampling = self.get_sampling()

        if not getattr(
            sampling,
            "qa_required",
            False,
        ):
            raise ValidationError(
                "Sampling QA approval is not required for this sample."
            )

        if getattr(
            sampling,
            "status",
            None,
        ) != "QA_REVIEW":
            raise ValidationError(
                "The sampling record is not awaiting QA review."
            )

        result = form.save()

        decision = str(
            form.cleaned_data.get(
                "decision",
                "",
            )
        ).upper()

        if decision in {
            "APPROVE",
            "PASS",
            "APPROVED",
        }:
            approve = getattr(
                sampling,
                "approve_weight_deviation",
                None,
            )

            if callable(approve):
                approve(
                    user=self.request.user
                )
            else:
                sampling.qa_approved = True

                if hasattr(
                    sampling,
                    "qa_approved_by",
                ):
                    sampling.qa_approved_by = (
                        self.request.user
                    )

                if hasattr(
                    sampling,
                    "qa_approved_at",
                ):
                    sampling.qa_approved_at = (
                        timezone.now()
                    )

                sampling.status = "COMPLETED"
                sampling.save()

        elif decision in {
            "REJECT",
            "REJECTED",
        }:
            sampling.qa_approved = False

            if hasattr(
                sampling,
                "qa_approved_by",
            ):
                sampling.qa_approved_by = (
                    self.request.user
                )

            if hasattr(
                sampling,
                "qa_approved_at",
            ):
                sampling.qa_approved_at = (
                    timezone.now()
                )

            sampling.save()

            process = self.get_process()

            process.status = (
                ChemicalAnalysisProcess.WorkflowStatus.REJECTED
            )

            process.save(
                update_fields=["status"]
            )

        else:
            raise ValidationError(
                "Invalid sampling QA decision."
            )

        return result


class StartAnalysisTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = StartAnalysisForm

    def save_form(self, form):
        process = self.get_process()

        if process.analysis_request is None:
            raise ValidationError(
                "An analysis request is required."
            )

        sampling = self.get_sampling()

        if getattr(
            sampling,
            "status",
            None,
        ) != "COMPLETED":
            raise ValidationError(
                "Systematic random sampling must be completed before chemical analysis."
            )

        if (
            getattr(
                sampling,
                "qa_required",
                False,
            )
            and not getattr(
                sampling,
                "qa_approved",
                False,
            )
        ):
            raise ValidationError(
                "Sampling QA approval is required before chemical analysis."
            )

        process.refresh_assigned_analysts()

        if not process.has_assigned_analysts:
            raise ValidationError(
                "No active analyst is currently assigned to this chemical analysis duty."
            )

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis."
            )

        process.mark_analysis_started(
            performed_by=self.request.user
        )

        return process


class RecordTestResultTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = BatchTestResultForm

    def get_retest_parameter_id(self):
        value = self.get_task_data().get(
            "retest_parameter_id"
        )

        if value in (
            None,
            "",
        ):
            return None

        try:
            return int(value)
        except (
            TypeError,
            ValueError,
        ):
            raise ValidationError(
                "The retest parameter reference is invalid."
            )

    def get_next_parameter(self):
        process = self.get_process()

        retest_parameter_id = (
            self.get_retest_parameter_id()
        )

        required = process.required_specifications()

        if retest_parameter_id is not None:
            parameter = (
                required
                .filter(
                    pk=retest_parameter_id
                )
                .first()
            )

            if parameter is None:
                raise ValidationError(
                    "The selected retest parameter is no longer required for this analysis."
                )

            return parameter

        completed = set(
            BatchTestResult.objects
            .filter(
                batch=process.batch
            )
            .exclude(
                status__isnull=True
            )
            .exclude(
                status=""
            )
            .values_list(
                "parameter_id",
                flat=True,
            )
        )

        return (
            required
            .exclude(
                pk__in=completed
            )
            .order_by("pk")
            .first()
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        process = self.get_process()

        process.refresh_assigned_analysts()

        if not process.has_assigned_analysts:
            raise ValidationError(
                "No active analyst is currently assigned to this chemical analysis duty."
            )

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis."
            )

        kwargs.update(
            {
                "process": process,
                "batch": self.get_batch(),
                "analyst": self.request.user,
            }
        )

        return kwargs

    def get_form(self):
        form = super().get_form()

        parameter = self.get_next_parameter()

        if parameter is None:
            raise ValidationError(
                "All required analytical parameters have already been completed."
            )

        if "parameter" in form.fields:
            form.fields[
                "parameter"
            ].queryset = (
                form.fields[
                    "parameter"
                ].queryset.filter(
                    pk=parameter.pk
                )
            )

            form.initial[
                "parameter"
            ] = parameter.pk

        return form

    def save_form(self, form):
        process = self.get_process()

        process.refresh_assigned_analysts()

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis."
            )

        parameter = form.cleaned_data.get(
            "parameter"
        )

        expected_parameter = (
            self.get_next_parameter()
        )

        if (
            parameter is None
            or expected_parameter is None
            or parameter.pk
            != expected_parameter.pk
        ):
            raise ValidationError(
                "The selected parameter is not the parameter currently required by the workflow."
            )

        result = form.save()

        if result.batch_id != process.batch_id:
            raise ValidationError(
                "The result belongs to another batch."
            )

        if result.parameter_id != parameter.pk:
            raise ValidationError(
                "The recorded result does not match the required analytical parameter."
            )

        self.set_task_data(
            result_id=result.pk,
            parameter_id=result.parameter_id,
        )

        return result


class RecordDynamicAnalysisInputTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = DynamicChemicalAnalysisInputForm

    def get_result_id(self):
        result_id = self.get_task_data().get(
            "result_id"
        )

        if result_id in (
            None,
            "",
        ):
            raise ValidationError(
                "No analytical test result is attached to this input task."
            )

        try:
            return int(result_id)
        except (
            TypeError,
            ValueError,
        ):
            raise ValidationError(
                "The analytical test result reference is invalid."
            )

    def get_test_result(self):
        process = self.get_process()

        process.refresh_assigned_analysts()

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis."
            )

        result = (
            BatchTestResult.objects
            .filter(
                pk=self.get_result_id(),
                batch=process.batch,
            )
            .select_related(
                "parameter",
                "parameter__method",
            )
            .first()
        )

        if result is None:
            raise ValidationError(
                "The analytical test result could not be found."
            )

        if (
            result.parameter is None
            or result.parameter.method is None
        ):
            raise ValidationError(
                "The selected analytical parameter has no analysis method."
            )

        fields = (
            result.parameter.method
            .get_input_fields()
        )

        if isinstance(
            fields,
            str,
        ):
            fields = [
                value.strip()
                for value in fields.split(",")
                if value.strip()
            ]

        if not fields:
            raise ValidationError(
                "The selected analytical method does not require method inputs."
            )

        return result

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs[
            "test_result"
        ] = self.get_test_result()

        return kwargs

    def save_form(self, form):
        test_result = self.get_test_result()

        inputs = form.as_input_dictionary()

        model_form = ChemicalAnalysisInputForm(
            data={
                "test_result": test_result.pk,
                "inputs": json.dumps(inputs),
            },
            test_result=test_result,
        )

        if not model_form.is_valid():
            raise ValidationError(
                model_form.errors.as_json()
            )

        return model_form.save()


class CompleteAnalysisTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = CompleteAnalysisForm

    def save_form(self, form):
        process = self.get_process()

        process.refresh_assigned_analysts()

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis."
            )

        if not process.is_analysis_complete:
            raise ValidationError(
                "All required analytical tests must be completed."
            )

        process.mark_analysis_completed(
            performed_by=self.request.user
        )

        return process


class CompleteRetestTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = ConfirmActionForm

    def save_form(self, form):
        process = self.get_process()

        if process.status != (
            ChemicalAnalysisProcess.WorkflowStatus.RETEST
        ):
            raise ValidationError(
                "The analysis is not currently in the retest stage."
            )

        process.refresh_assigned_analysts()

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis."
            )

        if not process.is_analysis_complete:
            raise ValidationError(
                "The required retest result has not been completed."
            )

        process.mark_analysis_completed(
            performed_by=self.request.user
        )

        self.set_task_data(
            retest_completed=True
        )

        return process


class QAReviewTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = QAReviewForm

    def save_form(self, form):
        process = self.get_process()

        if process.has_pending_tests:
            raise ValidationError(
                "All required analytical tests must be completed before QA review."
            )

        decision = str(
            form.cleaned_data.get(
                "decision",
                "",
            )
        ).upper()

        if decision not in {
            "PASS",
            "RETEST",
            "REJECT",
        }:
            raise ValidationError(
                "Invalid QA decision."
            )

        remarks = (
            form.cleaned_data.get(
                "remarks"
            )
            or ""
        ).strip()

        if (
            decision in {
                "RETEST",
                "REJECT",
            }
            and not remarks
        ):
            raise ValidationError(
                "Remarks are required for RETEST or REJECT decisions."
            )

        if (
            decision == "PASS"
            and process.failed_tests.exists()
        ):
            raise ValidationError(
                "A chemical analysis with failed results cannot be approved by QA."
            )

        process.qa_officer = self.request.user
        process.qa_reviewed_at = timezone.now()

        if decision == "RETEST":
            process.rework_count += 1
            process.status = (
                ChemicalAnalysisProcess.WorkflowStatus.RETEST
            )

        elif decision == "PASS":
            process.status = (
                ChemicalAnalysisProcess.WorkflowStatus.QA
            )

        else:
            process.status = (
                ChemicalAnalysisProcess.WorkflowStatus.REJECTED
            )

        process.save(
            update_fields=[
                "qa_officer",
                "qa_reviewed_at",
                "rework_count",
                "status",
            ]
        )

        if decision == "REJECT":
            batch = process.batch

            if batch is not None:
                batch.status = (
                    ChemicalBatch.Status.REJECTED
                )

                batch.save(
                    update_fields=["status"]
                )

        self.set_task_data(
            decision=decision,
            remarks=remarks,
        )

        return process


class RetestTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = RetestForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        process = self.get_process()

        process.refresh_assigned_analysts()

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis."
            )

        kwargs[
            "process"
        ] = process

        return kwargs

    def save_form(self, form):
        process = self.get_process()

        process.refresh_assigned_analysts()

        if not process.is_authorized_analyst(
            self.request.user
        ):
            raise PermissionDenied(
                "You are not currently assigned to perform this chemical analysis."
            )

        parameter = form.cleaned_data.get(
            "parameter"
        )

        if parameter is None:
            raise ValidationError(
                "A parameter must be selected for retesting."
            )

        if not process.required_specifications().filter(
            pk=parameter.pk
        ).exists():
            raise ValidationError(
                "The selected parameter is not required for this analysis."
            )

        reason = (
            form.cleaned_data.get(
                "reason"
            )
            or ""
        ).strip()

        if not reason:
            raise ValidationError(
                "A reason is required for a chemical retest."
            )

        self.set_task_data(
            retest_parameter_id=parameter.pk,
            retest_reason=reason,
        )

        process.status = (
            ChemicalAnalysisProcess.WorkflowStatus.RETEST
        )

        process.save(
            update_fields=["status"]
        )

        return parameter


class ApprovalTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = ApprovalForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def save_form(self, form):
        process = self.get_process()

        if process.status != (
            ChemicalAnalysisProcess.WorkflowStatus.QA
        ):
            raise ValidationError(
                "Chemical analysis approval is only available after QA review."
            )

        if process.has_pending_tests:
            raise ValidationError(
                "All required analytical tests must be completed before approval."
            )

        if process.failed_tests.exists():
            raise ValidationError(
                "An analysis with failed results cannot proceed to approval."
            )

        process.mark_approved(
            approved_by=self.request.user
        )

        self.set_task_data(
            decision="APPROVE"
        )

        return process


class ConfirmWorkflowActionTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = ConfirmActionForm

    def save_form(self, form):
        process = self.get_process()

        if process.status != (
            ChemicalAnalysisProcess.WorkflowStatus.APPROVED
        ):
            raise ValidationError(
                "Batch disposition is available only after chemical analysis approval and automatic CoA issuance."
            )

        batch = self.get_batch()

        if batch.status != ChemicalBatch.Status.APPROVED:
            raise ValidationError(
                "The chemical batch must be approved before disposition."
            )

        coa = (
            ChemicalCoA.objects
            .filter(
                batch=batch
            )
            .first()
        )

        if coa is None:
            raise ValidationError(
                "The Certificate of Analysis has not been automatically generated and issued."
            )

        if not coa.is_approved:
            raise ValidationError(
                "The Certificate of Analysis has not been automatically approved."
            )

        action = form.cleaned_data.get(
            "action"
        )

        normalized = str(
            action
        ).upper()

        if normalized not in {
            "UTILIZE",
            "RETURN",
        }:
            raise ValidationError(
                "Invalid batch disposition."
            )

        self.set_task_data(
            action=normalized
        )

        return form.cleaned_data


class UtilizeChemicalBatchTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = UtilizationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs[
            "batch"
        ] = self.get_batch()
        return kwargs

    def save_form(self, form):
        batch = self.get_batch()

        if batch.status != ChemicalBatch.Status.APPROVED:
            raise ValidationError(
                "Only an approved chemical batch can be utilized."
            )

        quantity = form.cleaned_data.get(
            "quantity_used"
        )

        if (
            quantity is not None
            and quantity > batch.quantity_received
        ):
            raise ValidationError(
                "Quantity utilized cannot exceed quantity received."
            )

        batch.status = (
            ChemicalBatch.Status.UTILIZED
        )

        batch.save(
            update_fields=["status"]
        )

        process = self.get_process()

        process.status = (
            ChemicalAnalysisProcess.WorkflowStatus.UTILIZED
        )

        process.completed_at = timezone.now()

        process.save(
            update_fields=[
                "status",
                "completed_at",
            ]
        )

        return batch


class ReturnChemicalBatchTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = ReturnToSupplierForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs[
            "batch"
        ] = self.get_batch()
        return kwargs

    def save_form(self, form):
        batch = self.get_batch()

        if batch.status != ChemicalBatch.Status.APPROVED:
            raise ValidationError(
                "Only an approved chemical batch can be returned."
            )

        quantity = form.cleaned_data.get(
            "quantity_returned"
        )

        if (
            quantity is not None
            and quantity > batch.quantity_received
        ):
            raise ValidationError(
                "Quantity returned cannot exceed quantity received."
            )

        batch.status = (
            ChemicalBatch.Status.RETURNED
        )

        batch.save(
            update_fields=["status"]
        )

        process = self.get_process()

        process.status = (
            ChemicalAnalysisProcess.WorkflowStatus.RETURNED
        )

        process.completed_at = timezone.now()

        process.save(
            update_fields=[
                "status",
                "completed_at",
            ]
        )

        return batch


class RejectAnalysisTaskView(
    ChemicalWorkflowTaskView,
):
    form_class = RejectAnalysisForm

    def save_form(self, form):
        process = self.get_process()

        process.status = (
            ChemicalAnalysisProcess.WorkflowStatus.REJECTED
        )

        process.save(
            update_fields=["status"]
        )

        batch = process.batch

        if batch is not None:
            if (
                batch.status
                != ChemicalBatch.Status.REJECTED
            ):
                batch.status = (
                    ChemicalBatch.Status.REJECTED
                )

                batch.save(
                    update_fields=["status"]
                )

        return process


class ChemicalAnalysisFlow(flow.Flow):
    process_class = ChemicalAnalysisProcess
    lock_impl = lock.select_for_update_lock

    start = (
        flow.Start(
            StartChemicalBatchView.as_view()
        )
        .Annotation(
            title="Receive Chemical Batch"
        )
        .Permission(
            "ca.receive_chemical_batch"
        )
        .Next(this.receive)
    )

    receive = (
        flow.View(
            ReceiveChemicalBatchTaskView.as_view()
        )
        .Annotation(
            title="Confirm Chemical Receipt"
        )
        .Permission(
            "ca.receive_chemical_batch"
        )
        .Next(this.create_request)
    )

    create_request = (
        flow.View(
            CreateChemicalAnalysisRequestTaskView.as_view()
        )
        .Annotation(
            title="Create Analysis Request"
        )
        .Permission(
            "ca.create_analysis_request"
        )
        .Next(this.checklist)
    )

    checklist = (
        flow.View(
            ChecklistTaskView.as_view()
        )
        .Annotation(
            title="Receiving Checklist"
        )
        .Permission(
            "ca.complete_receiving_checklist"
        )
        .Next(this.complete_checklist)
    )

    complete_checklist = (
        flow.View(
            CompleteChecklistTaskView.as_view()
        )
        .Annotation(
            title="Complete Receiving Checklist"
        )
        .Permission(
            "ca.complete_receiving_checklist"
        )
        .Next(this.systematic_sampling)
    )

    systematic_sampling = (
        flow.View(
            StartSystematicSamplingTaskView.as_view()
        )
        .Annotation(
            title="Generate Systematic Random Sampling Plan"
        )
        .Permission(
            "ca.perform_systematic_random_sampling"
        )
        .Next(
            this.record_sampling_measurements
        )
    )

    record_sampling_measurements = (
        flow.View(
            SystematicSamplingMeasurementTaskView.as_view()
        )
        .Annotation(
            title="Record Sample Measurements"
        )
        .Permission(
            "ca.perform_systematic_random_sampling"
        )
        .Next(
            this.sampling_counter_check
        )
    )

    sampling_counter_check = (
        flow.View(
            CounterCheckSystematicSamplingTaskView.as_view()
        )
        .Annotation(
            title="Counter Check Sampling"
        )
        .Permission(
            "ca.counter_check_systematic_sampling"
        )
        .Next(
            this.sampling_qa_decision
        )
    )

    sampling_qa_decision = (
        flow.If(
            this.sampling_qa_required
        )
        .Then(
            this.sampling_qa
        )
        .Else(
            this.start_analysis
        )
    )

    sampling_qa = (
        flow.View(
            SamplingQAApprovalTaskView.as_view()
        )
        .Annotation(
            title="Sampling QA Review"
        )
        .Permission(
            "ca.approve_sampling_weight_deviation"
        )
        .Next(
            this.sampling_qa_result
        )
    )

    sampling_qa_result = (
        flow.If(
            this.sampling_qa_passed
        )
        .Then(
            this.start_analysis
        )
        .Else(
            this.reject
        )
    )

    start_analysis = (
        flow.View(
            StartAnalysisTaskView.as_view()
        )
        .Annotation(
            title="Start Chemical Analysis"
        )
        .Permission(
            "ca.start_chemical_analysis"
        )
        .Next(
            this.record_result
        )
    )

    record_result = (
        flow.View(
            RecordTestResultTaskView.as_view()
        )
        .Annotation(
            title="Record Chemical Test Result"
        )
        .Permission(
            "ca.record_chemical_result"
        )
        .Next(
            this.check_result_input,
            task_data=lambda activation: {
                "result_id": (
                    activation.task.data.get(
                        "result_id"
                    )
                    if isinstance(
                        activation.task.data,
                        dict,
                    )
                    else None
                ),
                "parameter_id": (
                    activation.task.data.get(
                        "parameter_id"
                    )
                    if isinstance(
                        activation.task.data,
                        dict,
                    )
                    else None
                ),
                "retest_parameter_id": (
                    activation.task.data.get(
                        "retest_parameter_id"
                    )
                    if isinstance(
                        activation.task.data,
                        dict,
                    )
                    else None
                ),
            },
        )
    )

    check_result_input = (
        flow.If(
            this.result_requires_input
        )
        .Then(
            this.record_input
        )
        .Else(
            this.check_analysis_progress
        )
    )

    record_input = (
        flow.View(
            RecordDynamicAnalysisInputTaskView.as_view()
        )
        .Annotation(
            title="Record Method Inputs"
        )
        .Permission(
            "ca.record_chemical_result"
        )
        .Next(
            this.check_analysis_progress
        )
    )

    check_analysis_progress = (
        flow.If(
            this.analysis_complete
        )
        .Then(
            this.complete_analysis
        )
        .Else(
            this.record_result
        )
    )

    complete_analysis = (
        flow.View(
            CompleteAnalysisTaskView.as_view()
        )
        .Annotation(
            title="Complete Chemical Analysis"
        )
        .Permission(
            "ca.complete_chemical_analysis"
        )
        .Next(
            this.qa_review
        )
    )

    qa_review = (
        flow.View(
            QAReviewTaskView.as_view()
        )
        .Annotation(
            title="Review Chemical Analysis"
        )
        .Permission(
            "ca.review_chemical_analysis"
        )
        .Next(
            this.qa_decision,
            task_data=lambda activation: {
                "decision": (
                    activation.task.data.get(
                        "decision"
                    )
                    if isinstance(
                        activation.task.data,
                        dict,
                    )
                    else None
                ),
                "remarks": (
                    activation.task.data.get(
                        "remarks"
                    )
                    if isinstance(
                        activation.task.data,
                        dict,
                    )
                    else None
                ),
            },
        )
    )

    qa_decision = (
        flow.If(
            this.qa_is_retest
        )
        .Then(
            this.retest
        )
        .Else(
            flow.If(
                this.qa_is_rejected
            )
            .Then(
                this.reject
            )
            .Else(
                this.approval
            )
        )
    )

    retest = (
        flow.View(
            RetestTaskView.as_view()
        )
        .Annotation(
            title="Request Chemical Retest"
        )
        .Permission(
            "ca.perform_chemical_retest"
        )
        .Next(
            this.retest_result
        )
    )

    retest_result = (
        flow.View(
            RecordTestResultTaskView.as_view()
        )
        .Annotation(
            title="Record Retest Result"
        )
        .Permission(
            "ca.record_chemical_result"
        )
        .Next(
            this.check_retest_input,
            task_data=lambda activation: {
                "result_id": (
                    activation.task.data.get(
                        "result_id"
                    )
                    if isinstance(
                        activation.task.data,
                        dict,
                    )
                    else None
                ),
                "parameter_id": (
                    activation.task.data.get(
                        "parameter_id"
                    )
                    if isinstance(
                        activation.task.data,
                        dict,
                    )
                    else None
                ),
                "retest_parameter_id": (
                    activation.task.data.get(
                        "retest_parameter_id"
                    )
                    if isinstance(
                        activation.task.data,
                        dict,
                    )
                    else None
                ),
            },
        )
    )

    check_retest_input = (
        flow.If(
            this.result_requires_input
        )
        .Then(
            this.retest_input
        )
        .Else(
            this.complete_retest
        )
    )

    retest_input = (
        flow.View(
            RecordDynamicAnalysisInputTaskView.as_view()
        )
        .Annotation(
            title="Record Retest Method Inputs"
        )
        .Permission(
            "ca.record_chemical_result"
        )
        .Next(
            this.complete_retest
        )
    )

    complete_retest = (
        flow.View(
            CompleteRetestTaskView.as_view()
        )
        .Annotation(
            title="Complete Chemical Retest"
        )
        .Permission(
            "ca.perform_chemical_retest"
        )
        .Next(
            this.qa_review
        )
    )

    approval = (
        flow.View(
            ApprovalTaskView.as_view()
        )
        .Annotation(
            title="Approve Chemical Analysis"
        )
        .Permission(
            "ca.approve_chemical_batch"
        )
        .Next(
            this.auto_generate_coa
        )
    )

    auto_generate_coa = (
        flow.Function(
            this.generate_and_issue_coa
        )
        .Annotation(
            title="Automatically Generate and Issue Chemical CoA"
        )
        .Next(
            this.batch_disposition
        )
    )

    batch_disposition = (
        flow.View(
            ConfirmWorkflowActionTaskView.as_view()
        )
        .Annotation(
            title="Chemical Batch Disposition"
        )
        .Next(
            this.disposition_decision,
            task_data=lambda activation: {
                "action": (
                    activation.task.data.get(
                        "action"
                    )
                    if isinstance(
                        activation.task.data,
                        dict,
                    )
                    else None
                )
            },
        )
    )

    disposition_decision = (
        flow.If(
            this.disposition_is_utilize
        )
        .Then(
            this.utilize
        )
        .Else(
            this.return_to_supplier
        )
    )

    utilize = (
        flow.View(
            UtilizeChemicalBatchTaskView.as_view()
        )
        .Annotation(
            title="Utilize Chemical Batch"
        )
        .Permission(
            "ca.utilize_chemical_batch"
        )
        .Next(
            this.completed
        )
    )

    return_to_supplier = (
        flow.View(
            ReturnChemicalBatchTaskView.as_view()
        )
        .Annotation(
            title="Return Chemical Batch"
        )
        .Permission(
            "ca.return_chemical_batch"
        )
        .Next(
            this.completed
        )
    )

    reject = (
        flow.View(
            RejectAnalysisTaskView.as_view()
        )
        .Annotation(
            title="Reject Chemical Batch"
        )
        .Permission(
            "ca.reject_chemical_batch"
        )
        .Next(
            this.rejected
        )
    )

    rejected = (
        flow.End()
        .Annotation(
            title="Chemical Analysis Rejected"
        )
    )

    completed = (
        flow.End()
        .Annotation(
            title="Chemical Analysis Completed"
        )
    )

    def result_requires_input(
        self,
        activation,
    ):
        task_data = activation.task.data

        if not isinstance(
            task_data,
            dict,
        ):
            return False

        result_id = task_data.get(
            "result_id"
        )

        if result_id in (
            None,
            "",
        ):
            return False

        try:
            result_id = int(result_id)
        except (
            TypeError,
            ValueError,
        ):
            return False

        result = (
            BatchTestResult.objects
            .filter(
                pk=result_id,
                batch=activation.process.batch,
            )
            .select_related(
                "parameter",
                "parameter__method",
            )
            .first()
        )

        if result is None:
            return False

        parameter = result.parameter

        method = (
            parameter.method
            if parameter is not None
            else None
        )

        if method is None:
            return False

        fields = method.get_input_fields()

        if isinstance(
            fields,
            str,
        ):
            fields = [
                value.strip()
                for value in fields.split(",")
                if value.strip()
            ]

        return bool(fields)

    def analysis_complete(
        self,
        activation,
    ):
        return bool(
            activation.process.is_analysis_complete
        )

    def sampling_qa_required(
        self,
        activation,
    ):
        sampling = (
            SystematicRandomSampling.objects
            .filter(
                process=activation.process
            )
            .first()
        )

        if sampling is None:
            return False

        return bool(
            getattr(
                sampling,
                "qa_required",
                False,
            )
        )

    def sampling_qa_passed(
        self,
        activation,
    ):
        sampling = (
            SystematicRandomSampling.objects
            .filter(
                process=activation.process
            )
            .first()
        )

        if sampling is None:
            return False

        return bool(
            getattr(
                sampling,
                "qa_approved",
                False,
            )
        )

    def qa_is_retest(
        self,
        activation,
    ):
        data = activation.task.data

        if not isinstance(
            data,
            dict,
        ):
            return False

        return (
            str(
                data.get(
                    "decision",
                    "",
                )
            ).upper()
            == "RETEST"
        )

    def qa_is_rejected(
        self,
        activation,
    ):
        data = activation.task.data

        if not isinstance(
            data,
            dict,
        ):
            return False

        return (
            str(
                data.get(
                    "decision",
                    "",
                )
            ).upper()
            == "REJECT"
        )

    def disposition_is_utilize(
        self,
        activation,
    ):
        data = activation.task.data

        if not isinstance(
            data,
            dict,
        ):
            return False

        return (
            str(
                data.get(
                    "action",
                    "",
                )
            ).upper()
            == "UTILIZE"
        )

    def generate_and_issue_coa(
        self,
        activation,
    ):
        with transaction.atomic():
            process = activation.process

            if process.status != (
                ChemicalAnalysisProcess.WorkflowStatus.APPROVED
            ):
                raise ValidationError(
                    "The CoA can only be generated after chemical analysis approval."
                )

            batch = process.batch

            if batch is None:
                raise ValidationError(
                    "Cannot generate a CoA without a chemical batch."
                )

            if batch.status != ChemicalBatch.Status.APPROVED:
                raise ValidationError(
                    "The chemical batch must be approved before CoA generation."
                )

            approver = process.approver

            if approver is None:
                raise ValidationError(
                    "An analysis approver is required before automatic CoA approval."
                )

            coa, _ = (
                ChemicalCoA.objects
                .select_for_update()
                .get_or_create(
                    batch=batch
                )
            )

            coa.prepare_for_generation()

            coa.approve(
                approved_by=approver
            )

            coa.refresh_from_db()

            if not coa.is_approved:
                raise ValidationError(
                    "The automatically generated Certificate of Analysis could not be approved."
                )

            if not coa.pdf_file:
                raise ValidationError(
                    "The automatically generated Certificate of Analysis has no PDF file."
                )

            if not coa.qr_code:
                raise ValidationError(
                    "The automatically generated Certificate of Analysis has no QR code."
                )

            if (
                hasattr(
                    batch,
                    "coa_generated",
                )
                and not batch.coa_generated
            ):
                batch.coa_generated = True

                batch.save(
                    update_fields=[
                        "coa_generated"
                    ]
                )

            task_data = activation.task.data

            if not isinstance(
                task_data,
                dict,
            ):
                task_data = {}

            task_data.update(
                {
                    "coa_id": coa.pk,
                    "coa_generated": True,
                    "coa_approved": True,
                    "coa_issued": True,
                    "coa_approved_by_id": (
                        coa.approved_by_id
                    ),
                    "coa_approved_on": (
                        coa.approved_on.isoformat()
                        if coa.approved_on
                        else None
                    ),
                }
            )

            activation.task.data = task_data

            activation.task.save(
                update_fields=["data"]
            )

            activation.done()

            return coa