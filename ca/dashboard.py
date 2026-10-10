from __future__ import annotations

from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone as dt_timezone
from importlib.metadata import PackageNotFoundError, version as package_version
from statistics import median
from typing import Any

from .mixins import CaWanjalaMixin

from django.core.exceptions import FieldError, PermissionDenied
from django.db.models import Avg, Count, Max, Min, Q
from django.http import JsonResponse
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.generic import TemplateView

from .models import (
    BatchTestResult,
    ChemicalAnalysisInput,
    ChemicalAnalysisProcess,
    ChemicalAnalysisRequest,
    ChemicalBatch,
    ChemicalCoA,
    ChecklistForWaterTreatmentChemicalAnalysis,
)


DASHBOARD_SCHEMA_VERSION = "7.1"


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
    "approve_batch": "ca.approve_chemical_batch",
    "reject_batch": "ca.reject_chemical_batch",
    "generate_coa": "ca.approve_chemical_coa",
    "approve_coa": "ca.approve_chemical_coa",
    "utilize": "ca.utilize_chemical_batch",
    "return": "ca.return_chemical_batch",
}


PROCESS_STATUSES = {
    "CREATED",
    "RECEIVED",
    "REQUESTED",
    "CHECKLIST",
    "ANALYSIS",
    "RETEST",
    "QA",
    "APPROVED",
    "REJECTED",
    "UTILIZED",
    "RETURNED",
    "COMPLETED",
}


ACTIVE_PROCESS_STATUSES = {
    "CREATED",
    "RECEIVED",
    "REQUESTED",
    "CHECKLIST",
    "ANALYSIS",
    "RETEST",
    "QA",
    "APPROVED",
}


TERMINAL_PROCESS_STATUSES = {
    "REJECTED",
    "UTILIZED",
    "RETURNED",
    "COMPLETED",
}


ANALYSIS_STATUSES = {"ANALYSIS"}
RETEST_STATUSES = {"RETEST"}
QA_STATUSES = {"QA"}


PASS_STATUSES = {"PASS", "PASSED"}
FAIL_STATUSES = {"FAIL", "FAILED"}
NA_STATUSES = {"NA", "N/A", "NOT_APPLICABLE"}
PENDING_RESULT_STATUSES = {
    None,
    "",
    "PENDING",
    "INCOMPLETE",
}


BATCH_STATUSES = {
    "RECEIVED",
    "ANALYSED",
    "APPROVED",
    "REJECTED",
    "UTILIZED",
    "RETURNED",
}


REQUEST_STATUSES = {
    "PENDING",
    "IN_PROGRESS",
    "COMPLETED",
}


FLOW_NODE_DEFINITIONS = OrderedDict(
    [
        (
            "register",
            {
                "label": "Register",
                "status": "CREATED",
                "queue": "received",
                "permission": None,
            },
        ),
        (
            "receive",
            {
                "label": "Receive",
                "status": "RECEIVED",
                "queue": "request",
                "permission": CHEMICAL_PERMISSIONS["receive"],
            },
        ),
        (
            "create_request",
            {
                "label": "Create Analysis Request",
                "status": "REQUESTED",
                "queue": "checklist",
                "permission": CHEMICAL_PERMISSIONS["request"],
            },
        ),
        (
            "checklist",
            {
                "label": "Receiving Checklist",
                "status": "CHECKLIST",
                "queue": "checklist",
                "permission": CHEMICAL_PERMISSIONS["checklist"],
            },
        ),
        (
            "complete_checklist",
            {
                "label": "Complete Checklist",
                "status": "CHECKLIST",
                "queue": "analysis_ready",
                "permission": CHEMICAL_PERMISSIONS["checklist"],
            },
        ),
        (
            "start_analysis",
            {
                "label": "Start Analysis",
                "status": "ANALYSIS",
                "queue": "analysis",
                "permission": CHEMICAL_PERMISSIONS["start"],
            },
        ),
        (
            "record_result",
            {
                "label": "Record Result",
                "status": "ANALYSIS",
                "queue": "analysis",
                "permission": CHEMICAL_PERMISSIONS["result"],
            },
        ),
        (
            "record_input",
            {
                "label": "Record Method Input",
                "status": "ANALYSIS",
                "queue": "analysis",
                "permission": CHEMICAL_PERMISSIONS["result"],
            },
        ),
        (
            "check_analysis_progress",
            {
                "label": "Check Analysis Progress",
                "status": "ANALYSIS",
                "queue": "analysis",
                "permission": CHEMICAL_PERMISSIONS["result"],
            },
        ),
        (
            "complete_analysis",
            {
                "label": "Complete Analysis",
                "status": "ANALYSIS",
                "queue": "qa",
                "permission": CHEMICAL_PERMISSIONS["complete"],
            },
        ),
        (
            "qa_review",
            {
                "label": "QA Review",
                "status": "QA",
                "queue": "qa",
                "permission": CHEMICAL_PERMISSIONS["qa"],
            },
        ),
        (
            "qa_decision",
            {
                "label": "QA Decision",
                "status": "QA",
                "queue": "qa",
                "permission": CHEMICAL_PERMISSIONS["qa"],
            },
        ),
        (
            "retest",
            {
                "label": "Retest",
                "status": "RETEST",
                "queue": "retest",
                "permission": CHEMICAL_PERMISSIONS["retest"],
            },
        ),
        (
            "retest_result",
            {
                "label": "Retest Result",
                "status": "RETEST",
                "queue": "retest",
                "permission": CHEMICAL_PERMISSIONS["result"],
            },
        ),
        (
            "retest_input",
            {
                "label": "Retest Method Input",
                "status": "RETEST",
                "queue": "retest",
                "permission": CHEMICAL_PERMISSIONS["result"],
            },
        ),
        (
            "complete_retest",
            {
                "label": "Complete Retest",
                "status": "QA",
                "queue": "qa",
                "permission": CHEMICAL_PERMISSIONS["complete"],
            },
        ),
        (
            "capa",
            {
                "label": "CAPA",
                "status": "QA",
                "queue": "qa",
                "permission": CHEMICAL_PERMISSIONS["qa"],
            },
        ),
        (
            "approval",
            {
                "label": "Analysis Approval",
                "status": "QA",
                "queue": "approval",
                "permission": CHEMICAL_PERMISSIONS["approve_batch"],
            },
        ),
        (
            "generate_coa",
            {
                "label": "Generate CoA",
                "status": "APPROVED",
                "queue": "coa",
                "permission": CHEMICAL_PERMISSIONS["generate_coa"],
            },
        ),
        (
            "approve_coa",
            {
                "label": "Approve CoA",
                "status": "APPROVED",
                "queue": "coa_approval",
                "permission": CHEMICAL_PERMISSIONS["approve_coa"],
            },
        ),
        (
            "batch_disposition",
            {
                "label": "Batch Disposition",
                "status": "APPROVED",
                "queue": "disposition",
                "permission": None,
            },
        ),
        (
            "utilize",
            {
                "label": "Utilize",
                "status": "UTILIZED",
                "queue": "utilization",
                "permission": CHEMICAL_PERMISSIONS["utilize"],
            },
        ),
        (
            "return",
            {
                "label": "Return",
                "status": "RETURNED",
                "queue": "return",
                "permission": CHEMICAL_PERMISSIONS["return"],
            },
        ),
        (
            "reject",
            {
                "label": "Reject",
                "status": "REJECTED",
                "queue": "rejected",
                "permission": CHEMICAL_PERMISSIONS["reject_batch"],
            },
        ),
        (
            "completed",
            {
                "label": "Completed",
                "status": "COMPLETED",
                "queue": "completed",
                "permission": None,
            },
        ),
    ]
)


FLOW_EDGES = [
    ("register", "receive"),
    ("receive", "create_request"),
    ("create_request", "checklist"),
    ("checklist", "complete_checklist"),
    ("complete_checklist", "start_analysis"),
    ("start_analysis", "record_result"),
    ("record_result", "record_input"),
    ("record_result", "check_analysis_progress"),
    ("record_input", "check_analysis_progress"),
    ("check_analysis_progress", "record_result"),
    ("check_analysis_progress", "complete_analysis"),
    ("complete_analysis", "qa_review"),
    ("qa_review", "qa_decision"),
    ("qa_decision", "retest"),
    ("qa_decision", "capa"),
    ("qa_decision", "reject"),
    ("qa_decision", "approval"),
    ("retest", "retest_result"),
    ("retest_result", "retest_input"),
    ("retest_result", "complete_retest"),
    ("retest_input", "complete_retest"),
    ("complete_retest", "qa_review"),
    ("capa", "qa_review"),
    ("approval", "generate_coa"),
    ("generate_coa", "approve_coa"),
    ("approve_coa", "batch_disposition"),
    ("batch_disposition", "utilize"),
    ("batch_disposition", "return"),
    ("utilize", "completed"),
    ("return", "completed"),
    ("reject", "rejected"),
]


ACTION_DEFINITIONS = OrderedDict(
    [
        (
            "receive",
            {
                "label": "Receive Batch",
                "url": "ca:receive-batch",
                "permission": CHEMICAL_PERMISSIONS["receive"],
            },
        ),
        (
            "view_batches",
            {
                "label": "Chemical Batches",
                "url": "ca:batch-list",
                "permission": CHEMICAL_PERMISSIONS["view_workflow"],
            },
        ),
        (
            "view_requests",
            {
                "label": "Analysis Requests",
                "url": "ca:request-list",
                "permission": CHEMICAL_PERMISSIONS["request"],
            },
        ),
        (
            "view_processes",
            {
                "label": "Analysis Processes",
                "url": "ca:process-list",
                "permission": CHEMICAL_PERMISSIONS["view_workflow"],
            },
        ),
        (
            "my_tasks",
            {
                "label": "My Tasks",
                "url": "ca:my-tasks",
                "permission": CHEMICAL_PERMISSIONS["view_workflow"],
            },
        ),
        (
            "assignment",
            {
                "label": "Pending Assignment",
                "url": "ca:pending-analysis",
                "permission": CHEMICAL_PERMISSIONS["request"],
            },
        ),
        (
            "overdue",
            {
                "label": "Overdue Analysis",
                "url": "ca:overdue-analysis",
                "permission": CHEMICAL_PERMISSIONS["view_workflow"],
            },
        ),
        (
            "pending_analysis",
            {
                "label": "Pending Analysis",
                "url": "ca:pending-analysis",
                "permission": CHEMICAL_PERMISSIONS["start"],
            },
        ),
        (
            "results",
            {
                "label": "Results",
                "url": "ca:result-list",
                "permission": CHEMICAL_PERMISSIONS["result"],
            },
        ),
        (
            "specifications",
            {
                "label": "Specifications",
                "url": "ca:specification-list",
                "permission": CHEMICAL_PERMISSIONS["view_workflow"],
            },
        ),
        (
            "coas",
            {
                "label": "Certificates of Analysis",
                "url": "ca:coa-list",
                "permission": CHEMICAL_PERMISSIONS["approve_coa"],
            },
        ),
    ]
)


class DashboardView(CaWanjalaMixin, TemplateView):
    template_name = "ca/dashboard/pages/dashboard.html"
    permission_required_view = None

    def require_permission(self, permission: str) -> bool:
        return self.user_has_ca_permission(permission)

    def get(self, request, *args, **kwargs):
        wants_json = (
            "application/json" in request.headers.get("Accept", "")
            or (
                request.headers.get("HX-Request") == "true"
                and request.GET.get("refresh") in {"1", "true", "yes"}
            )
        )

        if wants_json:
            return self._json_response()

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self._dashboard_data())
        return context

    def _dashboard_data(self):
        processes = list(self._processes())
        batches = list(self._batches())
        requests = list(self._requests())
        results = list(self._results())
        coas = list(self._coas())
        checklists = list(self._checklists())
        inputs = list(self._inputs())

        process_by_batch = self._process_by_batch(processes)

        queue_counts = self.get_queue_counts(
            processes,
            requests,
            checklists,
            process_by_batch,
        )

        sla = self.get_sla_metrics(
            requests,
            process_by_batch,
        )

        quality = self.get_quality_metrics(
            processes,
            results,
        )

        coa_metrics = self.get_coa_metrics(
            processes,
            coas,
        )

        checklist_metrics = self.get_checklist_metrics(
            checklists,
        )

        data_quality = self.get_data_quality_metrics(
            batches,
            requests,
            results,
            processes,
            checklists,
            coas,
            process_by_batch,
        )

        risk_register = self.get_risk_register(
            batches,
            requests,
            results,
            processes,
            checklists,
            coas,
            process_by_batch,
        )

        operations = self.get_operational_summary(
            processes,
            batches,
            requests,
            results,
            checklists,
            coas,
            queue_counts,
        )

        stage_metrics = self.get_stage_metrics(
            processes,
            batches,
            requests,
            coas,
            queue_counts,
        )

        analyst_performance = self.get_analyst_performance(results)
        supplier_performance = self.get_supplier_performance(batches)
        chemical_performance = self.get_chemical_performance(batches)
        workload = self.get_user_workload(processes)
        performance = self.get_performance_summary(
            analyst_performance,
            supplier_performance,
            chemical_performance,
            workload,
        )

        quality_summary = self.get_quality_summary(
            quality,
            coa_metrics,
            checklist_metrics,
        )

        risk_summary = self.get_risk_summary(risk_register)

        counts = {
            "processes": len(processes),
            "batches": len(batches),
            "requests": len(requests),
            "results": len(results),
            "coas": len(coas),
            "checklists": len(checklists),
            "inputs": len(inputs),
        }

        workflow_health = self.get_workflow_health(
            queue_counts,
            sla,
            quality,
            data_quality,
            coa_metrics,
        )

        attention_items = self.get_attention_items(
            queue_counts,
            sla,
            quality,
            coa_metrics,
            checklist_metrics,
            data_quality,
        )

        recent_activity = self.get_recent_activity(
            batches,
            requests,
            processes,
            results,
            coas,
        )

        my_tasks = self.get_my_tasks(
            processes,
            requests,
        )

        aging = self.get_workflow_aging(processes)
        throughput = self.get_throughput_trends(
            batches,
            processes,
            results,
        )

        lifecycle_funnel = self.get_lifecycle_funnel(
            batches,
            requests,
            processes,
            coas,
            process_by_batch,
        )

        result_distribution = self.get_result_distribution(results)
        parameter_analytics = self.get_parameter_analytics()
        risk_register = risk_register

        return {
            "dashboard_schema_version": DASHBOARD_SCHEMA_VERSION,
            "dashboard_contract": self.get_dashboard_contract(),
            "permissions": self.get_permissions(),
            "dashboard_actions": self.get_dashboard_actions(),
            "plant_context": self.get_plant_context(),
            "viewflow_version": self.get_viewflow_version(),
            "workflow_nodes": self.get_workflow_nodes(
                queue_counts,
                processes,
            ),
            "workflow_edges": [
                {
                    "from": source,
                    "to": target,
                }
                for source, target in FLOW_EDGES
            ],
            "counts": counts,
            "queue_counts": queue_counts,
            "sla": sla,
            "quality": quality,
            "coa_metrics": coa_metrics,
            "checklist_metrics": checklist_metrics,
            "data_quality": data_quality,
            "operations": operations,
            "stage_metrics": stage_metrics,
            "analyst_performance": analyst_performance,
            "supplier_performance": supplier_performance,
            "chemical_performance": chemical_performance,
            "workload": workload,
            "performance": performance,
            "quality_summary": quality_summary,
            "risk_summary": risk_summary,
            "workflow_health": workflow_health,
            "attention_items": attention_items,
            "recent_activity": recent_activity,
            "my_tasks": my_tasks,
            "aging": aging,
            "throughput": throughput,
            "lifecycle_funnel": lifecycle_funnel,
            "result_distribution": result_distribution,
            "parameter_analytics": parameter_analytics,
            "risk_register": risk_register,
            "analysis_inputs": self._serialize_inputs(inputs),
        }

    def get_permissions(self):
        superuser = self._is_superuser()
        user = self.request.user

        if superuser:
            flags = {
                key: True
                for key in CHEMICAL_PERMISSIONS
            }
        else:
            flags = {
                key: self.user_has_ca_permission(permission)
                for key, permission in CHEMICAL_PERMISSIONS.items()
            }

        flags.update(
            {
                "is_superuser": superuser,
                "view_workflow": superuser or user.has_perm("ca.view_chemicalanalysisprocess"),
                "view_process": superuser or user.has_perm("ca.view_chemicalanalysisprocess"),
                "view_chemicalbatch": superuser or user.has_perm("ca.view_chemicalbatch") or flags.get("receive", False),
                "view_chemicalcoa": superuser or user.has_perm("ca.view_chemicalcoa") or flags.get("approve_coa", False),
                "view_batchtestresult": superuser or user.has_perm("ca.view_batchtestresult") or flags.get("result", False),
                "view_chemicalspecification": superuser or user.has_perm("ca.view_chemicalspecification"),
                "view_chemicalrequest": superuser or user.has_perm("ca.view_chemicalanalysisrequest") or flags.get("request", False),
                "view_checklist": superuser or user.has_perm("ca.view_checklistforwatertreatmentchemicalanalysis") or flags.get("checklist", False),
                "receive_chemical_batch": flags.get("receive", False),
                "create_analysis_request": flags.get("request", False),
                "complete_checklist": flags.get("checklist", False),
                "start_analysis": flags.get("start", False),
                "record_result": flags.get("result", False),
                "complete_analysis": flags.get("complete", False),
                "retest": flags.get("retest", False),
                "qa_review": flags.get("qa", False),
                "approve_chemical_batch": flags.get("approve_batch", False),
                "reject_chemical_batch": flags.get("reject_batch", False),
                "approve_chemical_coa": flags.get("approve_coa", False),
                "verify_coa": superuser or user.has_perm("ca.verify_chemical_coa"),
                "utilize_chemical_batch": flags.get("utilize", False),
                "return_chemical_batch": flags.get("return", False),
                "reopen_checklist": flags.get("reopen_checklist", False),
                "has_any_ca_perm": superuser or any(flags.values()),
            }
        )
        return flags

    def get_dashboard_actions(self):
        permissions = self.get_permissions()
        actions = []

        for key, definition in ACTION_DEFINITIONS.items():
            permission_key = self._permission_key(
                definition.get("permission")
            )

            allowed = True
            if permission_key:
                allowed = permissions.get(permission_key, False)

            if not allowed:
                continue

            actions.append(
                {
                    "key": key,
                    "label": definition["label"],
                    "url": self.safe_reverse(
                        definition["url"]
                    ),
                    "permission": definition.get("permission"),
                }
            )

        return actions

    def get_dashboard_contract(self):
        return {
            "schema_version": DASHBOARD_SCHEMA_VERSION,
            "engine": "django-viewflow",
            "flow": "ChemicalAnalysisFlow",
            "sampling": False,
            "random_sampling": False,
            "systematic_sampling": False,
            "manual_analyst_assignment": True,
            "automatic_analyst_assignment": True,
            "automatic_assignment_delay_minutes": 30,
            "stages": [
                "REGISTER",
                "RECEIVE",
                "CREATE_REQUEST",
                "CHECKLIST",
                "COMPLETE_CHECKLIST",
                "START_ANALYSIS",
                "RECORD_RESULT",
                "RECORD_METHOD_INPUT",
                "COMPLETE_ANALYSIS",
                "QA_REVIEW",
                "QA_DECISION",
                "RETEST",
                "RETEST_RESULT",
                "RETEST_METHOD_INPUT",
                "COMPLETE_RETEST",
                "CAPA",
                "APPROVAL",
                "COA_GENERATION",
                "COA_APPROVAL",
                "DISPOSITION",
                "UTILIZATION",
                "RETURN",
                "REJECTION",
                "COMPLETE",
            ],
            "queues": [
                "received",
                "request",
                "checklist",
                "assignment_pending",
                "assignment_overdue",
                "analysis_ready",
                "analysis",
                "retest",
                "qa",
                "approval",
                "coa",
                "coa_approval",
                "disposition",
                "utilization",
                "return",
                "rejected",
                "completed",
                "overdue",
                "due_soon",
            ],
            "assignment": {
                "manual_allowed": True,
                "automatic_allowed": True,
                "automatic_after_minutes": 30,
                "manual_before_deadline": True,
                "automatic_after_deadline": True,
            },
            "result_inputs": {
                "dynamic_method_inputs": True,
            },
        }

    def _processes(self):
        queryset = (
            ChemicalAnalysisProcess.objects
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
                "batch__test_results",
            )
            .order_by("-updated_at", "-pk")
        )

        if not (
            self._is_superuser()
            or self.user_has_ca_permission("ca.view_chemicalanalysisprocess")
        ):
            user = self.request.user
            queryset = queryset.filter(
                Q(assigned_analyst=user)
                | Q(initiated_by=user)
                | Q(qa_officer=user)
                | Q(approver=user)
            )

        return self._scope_queryset(
            queryset,
            "batch__treatment_plant_id",
        )

    def _batches(self):
        if not (
            self._is_superuser()
            or self.user_has_ca_permission("ca.view_chemicalbatch")
            or self.user_has_ca_permission("ca.receive_chemical_batch")
            or self.user_has_ca_permission("ca.approve_chemical_batch")
            or self.user_has_ca_permission("ca.view_chemicalanalysisprocess")
        ):
            return ChemicalBatch.objects.none()

        queryset = (
            ChemicalBatch.objects
            .select_related(
                "chemical",
                "supplier",
                "treatment_plant",
                "received_by",
            )
            .prefetch_related("test_results")
            .order_by("-updated_at", "-pk")
        )

        return self._scope_queryset(
            queryset,
            "treatment_plant_id",
        )

    def _requests(self):
        queryset = (
            ChemicalAnalysisRequest.objects
            .select_related(
                "batch",
                "batch__chemical",
                "batch__supplier",
                "batch__treatment_plant",
                "requested_by",
                "received_by",
            )
            .prefetch_related("assigned_analysts")
            .order_by("-updated_at", "-pk")
        )

        if not (
            self._is_superuser()
            or self.user_has_ca_permission("ca.view_chemicalanalysisprocess")
            or self.user_has_ca_permission("ca.view_chemicalanalysisrequest")
            or self.user_has_ca_permission("ca.create_analysis_request")
        ):
            user = self.request.user
            queryset = queryset.filter(
                Q(requested_by=user)
                | Q(received_by=user)
                | Q(assigned_analysts=user)
            )

        return self._scope_queryset(
            queryset,
            "batch__treatment_plant_id",
        )

    def _results(self):
        queryset = (
            BatchTestResult.objects
            .select_related(
                "batch",
                "batch__chemical",
                "batch__treatment_plant",
                "parameter",
                "analyst",
            )
            .order_by("-tested_at", "-pk")
        )

        if not (
            self._is_superuser()
            or self.user_has_ca_permission("ca.view_batchtestresult")
            or self.user_has_ca_permission("ca.view_chemicalanalysisprocess")
        ):
            user = self.request.user
            queryset = queryset.filter(analyst=user)

        return self._scope_queryset(
            queryset,
            "batch__treatment_plant_id",
        )

    def _coas(self):
        if not (
            self._is_superuser()
            or self.user_has_ca_permission("ca.view_chemicalcoa")
            or self.user_has_ca_permission("ca.approve_chemical_coa")
            or self.user_has_ca_permission("ca.verify_chemical_coa")
            or self.user_has_ca_permission("ca.view_chemicalanalysisprocess")
        ):
            return ChemicalCoA.objects.none()

        queryset = (
            ChemicalCoA.objects
            .select_related(
                "batch",
                "batch__chemical",
                "batch__supplier",
                "batch__treatment_plant",
            )
            .order_by("-updated_at", "-pk")
        )

        return self._scope_queryset(
            queryset,
            "batch__treatment_plant_id",
        )

    def _checklists(self):
        if not (
            self._is_superuser()
            or self.user_has_ca_permission("ca.view_checklistforwatertreatmentchemicalanalysis")
            or self.user_has_ca_permission("ca.complete_receiving_checklist")
            or self.user_has_ca_permission("ca.view_chemicalanalysisprocess")
        ):
            return ChecklistForWaterTreatmentChemicalAnalysis.objects.none()

        queryset = (
            ChecklistForWaterTreatmentChemicalAnalysis.objects
            .select_related(
                "chemical_analysis_request",
                "chemical_analysis_request__batch",
                "chemical_analysis_request__batch__chemical",
                "chemical_analysis_request__batch__treatment_plant",
            )
            .order_by("-updated_at", "-pk")
        )

        return self._scope_queryset(
            queryset,
            "chemical_analysis_request__batch__treatment_plant_id",
        )

    def _inputs(self):
        queryset = (
            ChemicalAnalysisInput.objects
            .select_related(
                "test_result",
                "test_result__batch",
                "test_result__batch__treatment_plant",
                "test_result__parameter",
            )
            .order_by("-pk")
        )

        if not (
            self._is_superuser()
            or self.user_has_ca_permission("ca.view_batchtestresult")
            or self.user_has_ca_permission("ca.record_chemical_result")
            or self.user_has_ca_permission("ca.view_chemicalanalysisprocess")
        ):
            user = self.request.user
            queryset = queryset.filter(test_result__analyst=user)

        return self._scope_queryset(
            queryset,
            "test_result__batch__treatment_plant_id",
        )

    def _scope_queryset(self, queryset, field_name):
        return self.scope_queryset(queryset, field=field_name)

    def _process_by_batch(self, processes):
        latest = {}

        for process in processes:
            batch_id = getattr(process, "batch_id", None)

            if not batch_id:
                continue

            existing = latest.get(batch_id)

            if existing is None:
                latest[batch_id] = process
                continue

            current_timestamp = self._timestamp(
                getattr(process, "updated_at", None)
                or getattr(process, "created_at", None)
            )

            existing_timestamp = self._timestamp(
                getattr(existing, "updated_at", None)
                or getattr(existing, "created_at", None)
            )

            if current_timestamp >= existing_timestamp:
                latest[batch_id] = process

        return latest

    def get_process_counts(self, processes):
        return Counter(
            self._normalize_status(
                getattr(process, "status", None)
            )
            for process in processes
        )

    def get_batch_counts(self, batches):
        return Counter(
            self._normalize_status(
                getattr(batch, "status", None)
            )
            for batch in batches
        )

    def get_request_counts(self, requests):
        return Counter(
            self._normalize_status(
                getattr(request, "status", None)
            )
            for request in requests
        )

    def get_result_counts(self, results):
        return Counter(
            self._normalize_result_status(
                getattr(result, "status", None)
            )
            for result in results
        )

    def get_queue_counts(
        self,
        processes,
        requests,
        checklists,
        process_by_batch,
    ):
        queues = {
            "received": 0,
            "request": 0,
            "checklist": 0,
            "assignment_pending": 0,
            "assignment_overdue": 0,
            "analysis_ready": 0,
            "analysis": 0,
            "retest": 0,
            "qa": 0,
            "approval": 0,
            "coa": 0,
            "coa_approval": 0,
            "disposition": 0,
            "utilization": 0,
            "return": 0,
            "rejected": 0,
            "completed": 0,
            "overdue": 0,
            "due_soon": 0,
        }

        status_counts = self.get_process_counts(processes)
        request_counts = self.get_request_counts(requests)

        for process in processes:
            status = self._normalize_status(
                getattr(process, "status", None)
            )

            if status == "CREATED":
                queues["received"] += 1

            elif status == "RECEIVED":
                queues["request"] += 1

            elif status == "REQUESTED":
                queues["checklist"] += 1

            elif status == "CHECKLIST":
                if self._process_is_analysis_ready(process):
                    queues["analysis_ready"] += 1
                else:
                    queues["checklist"] += 1

            elif status == "ANALYSIS":
                if self._process_is_analysis_ready(process):
                    queues["analysis"] += 1
                else:
                    queues["analysis_ready"] += 1

            elif status == "RETEST":
                queues["retest"] += 1

            elif status == "QA":
                if self._process_requires_approval(process):
                    queues["approval"] += 1
                else:
                    queues["qa"] += 1

            elif status == "APPROVED":
                if not self._process_has_coa(process):
                    queues["coa"] += 1
                elif not self._process_has_approved_coa(process):
                    queues["coa_approval"] += 1
                else:
                    queues["disposition"] += 1

            elif status == "REJECTED":
                queues["rejected"] += 1

            elif status == "UTILIZED":
                queues["utilization"] += 1

            elif status == "RETURNED":
                queues["return"] += 1

            elif status == "COMPLETED":
                queues["completed"] += 1

        now = timezone.now()
        assignment_deadline = timedelta(minutes=30)

        for request in requests:
            status = self._normalize_status(
                getattr(request, "status", None)
            )

            if status not in {
                "PENDING",
                "IN_PROGRESS",
            }:
                continue

            assigned = self._request_has_assigned_analysts(request)

            if not assigned:
                deadline = self._request_assignment_deadline(request)

                if deadline:
                    if deadline <= now:
                        queues["assignment_overdue"] += 1
                    else:
                        queues["assignment_pending"] += 1
                else:
                    created_at = (
                        getattr(request, "created_at", None)
                        or getattr(request, "requested_at", None)
                    )

                    if created_at:
                        deadline = created_at + assignment_deadline

                        if deadline <= now:
                            queues["assignment_overdue"] += 1
                        else:
                            queues["assignment_pending"] += 1

            deadline = self._request_deadline(request)

            if (
                deadline
                and status != "COMPLETED"
            ):
                if deadline <= now:
                    queues["overdue"] += 1
                elif deadline <= now + timedelta(hours=2):
                    queues["due_soon"] += 1

        for checklist in checklists:
            if self._checklist_expired_incomplete(checklist):
                queues["overdue"] += 1

        queues["process_total"] = len(processes)
        queues["request_total"] = len(requests)
        queues["status_counts"] = dict(status_counts)
        queues["request_status_counts"] = dict(request_counts)

        queues["active_total"] = sum(
            queues[key]
            for key in (
                "received",
                "request",
                "checklist",
                "assignment_pending",
                "assignment_overdue",
                "analysis_ready",
                "analysis",
                "retest",
                "qa",
                "approval",
                "coa",
                "coa_approval",
                "disposition",
            )
        )

        queues["exception_total"] = (
            queues["overdue"]
            + queues["assignment_overdue"]
        )

        return queues

    def get_sla_metrics(self, requests, process_by_batch=None):
        now = timezone.now()

        active = 0
        completed = 0
        overdue = 0
        due_soon = 0
        turnaround_values = []
        records = []

        for request in requests:
            status = self._normalize_status(
                getattr(request, "status", None)
            )

            deadline = self._request_deadline(request)

            completed_at = getattr(
                request,
                "completed_at",
                None,
            )

            created_at = getattr(
                request,
                "created_at",
                None,
            ) or getattr(
                request,
                "requested_at",
                None,
            )

            is_completed = (
                status == "COMPLETED"
                or completed_at is not None
            )

            if is_completed:
                completed += 1

                if created_at and completed_at:
                    hours = max(
                        0,
                        (
                            self._aware(completed_at)
                            - self._aware(created_at)
                        ).total_seconds()
                        / 3600,
                    )
                    turnaround_values.append(hours)

            else:
                active += 1

            is_overdue = (
                bool(deadline)
                and not is_completed
                and deadline <= now
            )

            is_due_soon = (
                bool(deadline)
                and not is_completed
                and deadline > now
                and deadline <= now + timedelta(hours=2)
            )

            if is_overdue:
                overdue += 1

            if is_due_soon:
                due_soon += 1

            if deadline:
                records.append(
                    {
                        "request_id": getattr(request, "pk", None),
                        "batch_id": getattr(request, "batch_id", None),
                        "status": status,
                        "deadline": self._iso(deadline),
                        "overdue": is_overdue,
                        "due_soon": is_due_soon,
                        "overdue_hours": (
                            self._hours_since(deadline)
                            if is_overdue
                            else 0
                        ),
                    }
                )

        records.sort(
            key=lambda item: (
                not item["overdue"],
                -self._number(item["overdue_hours"]),
            )
        )

        average_turnaround = (
            sum(turnaround_values) / len(turnaround_values)
            if turnaround_values
            else 0
        )

        median_turnaround = (
            median(turnaround_values)
            if turnaround_values
            else 0
        )

        return {
            "active": active,
            "completed": completed,
            "overdue": overdue,
            "due_soon": due_soon,
            "turnaround_hours_average": round(
                average_turnaround,
                2,
            ),
            "turnaround_hours_median": round(
                median_turnaround,
                2,
            ),
            "records": records[:100],
            "compliance_rate": round(
                (
                    ((completed - overdue) / completed) * 100
                    if completed
                    else 100
                ),
                2,
            ),
        }

    def get_quality_metrics(self, processes, results):
        result_counts = self.get_result_counts(results)

        passed = sum(
            result_counts.get(status, 0)
            for status in PASS_STATUSES
        )

        failed = sum(
            result_counts.get(status, 0)
            for status in FAIL_STATUSES
        )

        na = sum(
            result_counts.get(status, 0)
            for status in NA_STATUSES
        )

        pending = sum(
            result_counts.get(status, 0)
            for status in PENDING_RESULT_STATUSES
        )

        evaluated = passed + failed

        process_statuses = self.get_process_counts(processes)

        rework_count = sum(
            1
            for process in processes
            if self._normalize_status(
                getattr(process, "status", None)
            ) == "RETEST"
        )

        return {
            "total_results": len(results),
            "passed": passed,
            "failed": failed,
            "na": na,
            "pending": pending,
            "evaluated": evaluated,
            "pass_rate": round(
                passed / evaluated * 100
                if evaluated
                else 0,
                2,
            ),
            "failure_rate": round(
                failed / evaluated * 100
                if evaluated
                else 0,
                2,
            ),
            "completed_processes": process_statuses.get(
                "COMPLETED",
                0,
            ),
            "approved_processes": process_statuses.get(
                "APPROVED",
                0,
            ),
            "rejected_processes": process_statuses.get(
                "REJECTED",
                0,
            ),
            "rework_count": rework_count,
        }

    def get_coa_metrics(self, processes, coas):
        total = len(coas)

        approved = sum(
            1
            for coa in coas
            if self._coa_is_approved(coa)
        )

        verified = sum(
            1
            for coa in coas
            if self._normalize_status(
                getattr(coa, "status", None)
            ) == "VERIFIED"
        )

        failed_integrity = sum(
            1
            for coa in coas
            if (
                getattr(coa, "integrity_valid", None) is False
                or getattr(coa, "hash_valid", None) is False
            )
        )

        assets_complete = sum(
            1
            for coa in coas
            if self._coa_assets_available(coa)
        )

        approved_processes = sum(
            1
            for process in processes
            if self._normalize_status(
                getattr(process, "status", None)
            ) == "APPROVED"
        )

        processes_with_coa = {
            getattr(coa, "batch_id", None)
            for coa in coas
            if getattr(coa, "batch_id", None)
        }

        approved_without_coa = sum(
            1
            for process in processes
            if (
                self._normalize_status(
                    getattr(process, "status", None)
                ) == "APPROVED"
                and getattr(process, "batch_id", None)
                not in processes_with_coa
            )
        )

        return {
            "total": total,
            "approved": approved,
            "verified": verified,
            "failed_integrity": failed_integrity,
            "assets_complete": assets_complete,
            "approved_without_coa": approved_without_coa,
            "approval_rate": round(
                approved / total * 100
                if total
                else 0,
                2,
            ),
            "verification_rate": round(
                verified / total * 100
                if total
                else 0,
                2,
            ),
            "asset_completion_rate": round(
                assets_complete / total * 100
                if total
                else 0,
                2,
            ),
        }

    def get_checklist_metrics(self, checklists):
        total = len(checklists)

        completed = sum(
            1
            for checklist in checklists
            if self._checklist_is_complete(checklist)
        )

        expired = sum(
            1
            for checklist in checklists
            if self._checklist_is_expired(checklist)
        )

        incomplete = total - completed

        incomplete_expired = sum(
            1
            for checklist in checklists
            if (
                not self._checklist_is_complete(checklist)
                and self._checklist_is_expired(checklist)
            )
        )

        pending = max(
            0,
            incomplete - incomplete_expired,
        )

        return {
            "total": total,
            "completed": completed,
            "expired": expired,
            "incomplete": incomplete,
            "incomplete_expired": incomplete_expired,
            "pending": pending,
            "completion_rate": round(
                completed / total * 100
                if total
                else 0,
                2,
            ),
        }

    def get_parameter_analytics(self):
        results = self._results()

        try:
            rows = (
                results
                .values(
                    "parameter_id",
                    "parameter__name",
                    "parameter__unit",
                )
                .annotate(
                    total=Count("id"),
                    passed=Count(
                        "id",
                        filter=Q(
                            status__in=PASS_STATUSES
                        ),
                    ),
                    failed=Count(
                        "id",
                        filter=Q(
                            status__in=FAIL_STATUSES
                        ),
                    ),
                    na=Count(
                        "id",
                        filter=Q(
                            status__in=NA_STATUSES
                        ),
                    ),
                    average=Avg("value"),
                    minimum=Min("value"),
                    maximum=Max("value"),
                    latest_test=Max("tested_at"),
                )
                .order_by(
                    "parameter__name"
                )
            )
        except FieldError:
            return []

        output = []

        for row in rows:
            evaluated = (
                row["passed"]
                + row["failed"]
            )

            output.append(
                {
                    "parameter_id": row["parameter_id"],
                    "name": row["parameter__name"],
                    "unit": row["parameter__unit"],
                    "total": row["total"],
                    "passed": row["passed"],
                    "failed": row["failed"],
                    "na": row["na"],
                    "average": self._number(
                        row["average"]
                    ),
                    "minimum": self._number(
                        row["minimum"]
                    ),
                    "maximum": self._number(
                        row["maximum"]
                    ),
                    "latest_test": self._iso(
                        row["latest_test"]
                    ),
                    "pass_rate": round(
                        row["passed"] / evaluated * 100
                        if evaluated
                        else 0,
                        2,
                    ),
                }
            )

        return output

    def get_analyst_performance(self, results):
        try:
            queryset = (
                self._results()
                .values(
                    "analyst_id",
                    "analyst__username",
                )
                .annotate(
                    total=Count("id"),
                    passed=Count(
                        "id",
                        filter=Q(
                            status__in=PASS_STATUSES
                        ),
                    ),
                    failed=Count(
                        "id",
                        filter=Q(
                            status__in=FAIL_STATUSES
                        ),
                    ),
                    na=Count(
                        "id",
                        filter=Q(
                            status__in=NA_STATUSES
                        ),
                    ),
                    latest_test=Max("tested_at"),
                )
                .order_by(
                    "-total",
                    "analyst__username",
                )
            )
        except FieldError:
            return []

        output = []

        for row in queryset:
            evaluated = (
                row["passed"]
                + row["failed"]
            )

            output.append(
                {
                    "analyst_id": row["analyst_id"],
                    "username": (
                        row["analyst__username"]
                        or "Unassigned"
                    ),
                    "total": row["total"],
                    "passed": row["passed"],
                    "failed": row["failed"],
                    "na": row["na"],
                    "pass_rate": round(
                        row["passed"] / evaluated * 100
                        if evaluated
                        else 0,
                        2,
                    ),
                    "latest_test": self._iso(
                        row["latest_test"]
                    ),
                }
            )

        return output

    def get_supplier_performance(self, batches=None):
        queryset = self._batches()

        try:
            rows = (
                queryset
                .values(
                    "supplier_id",
                    "supplier__name",
                )
                .annotate(
                    batches=Count(
                        "id",
                        distinct=True,
                    ),
                    results=Count(
                        "test_results",
                        distinct=True,
                    ),
                    passed=Count(
                        "test_results",
                        filter=Q(
                            test_results__status__in=PASS_STATUSES
                        ),
                        distinct=True,
                    ),
                    failed=Count(
                        "test_results",
                        filter=Q(
                            test_results__status__in=FAIL_STATUSES
                        ),
                        distinct=True,
                    ),
                    na=Count(
                        "test_results",
                        filter=Q(
                            test_results__status__in=NA_STATUSES
                        ),
                        distinct=True,
                    ),
                    received=Count(
                        "id",
                        filter=Q(
                            status="RECEIVED"
                        ),
                        distinct=True,
                    ),
                    approved=Count(
                        "id",
                        filter=Q(
                            status="APPROVED"
                        ),
                        distinct=True,
                    ),
                    rejected=Count(
                        "id",
                        filter=Q(
                            status="REJECTED"
                        ),
                        distinct=True,
                    ),
                    utilized=Count(
                        "id",
                        filter=Q(
                            status="UTILIZED"
                        ),
                        distinct=True,
                    ),
                    returned=Count(
                        "id",
                        filter=Q(
                            status="RETURNED"
                        ),
                        distinct=True,
                    ),
                )
                .order_by(
                    "-batches",
                    "supplier__name",
                )
            )
        except FieldError:
            return []

        output = []

        for row in rows:
            evaluated = (
                row["passed"]
                + row["failed"]
            )

            output.append(
                {
                    "supplier_id": row["supplier_id"],
                    "name": (
                        row["supplier__name"]
                        or "Unspecified"
                    ),
                    "batches": row["batches"],
                    "results": row["results"],
                    "passed": row["passed"],
                    "failed": row["failed"],
                    "na": row["na"],
                    "received": row["received"],
                    "approved": row["approved"],
                    "rejected": row["rejected"],
                    "utilized": row["utilized"],
                    "returned": row["returned"],
                    "pass_rate": round(
                        row["passed"] / evaluated * 100
                        if evaluated
                        else 0,
                        2,
                    ),
                    "failure_rate": round(
                        row["failed"] / evaluated * 100
                        if evaluated
                        else 0,
                        2,
                    ),
                }
            )

        return output

    def get_chemical_performance(self, batches=None):
        queryset = self._batches()

        try:
            rows = (
                queryset
                .values(
                    "chemical_id",
                    "chemical__name",
                    "chemical__code",
                )
                .annotate(
                    batches=Count(
                        "id",
                        distinct=True,
                    ),
                    results=Count(
                        "test_results",
                        distinct=True,
                    ),
                    passed=Count(
                        "test_results",
                        filter=Q(
                            test_results__status__in=PASS_STATUSES
                        ),
                        distinct=True,
                    ),
                    failed=Count(
                        "test_results",
                        filter=Q(
                            test_results__status__in=FAIL_STATUSES
                        ),
                        distinct=True,
                    ),
                    na=Count(
                        "test_results",
                        filter=Q(
                            test_results__status__in=NA_STATUSES
                        ),
                        distinct=True,
                    ),
                    received=Count(
                        "id",
                        filter=Q(
                            status="RECEIVED"
                        ),
                        distinct=True,
                    ),
                    approved=Count(
                        "id",
                        filter=Q(
                            status="APPROVED"
                        ),
                        distinct=True,
                    ),
                    rejected=Count(
                        "id",
                        filter=Q(
                            status="REJECTED"
                        ),
                        distinct=True,
                    ),
                    utilized=Count(
                        "id",
                        filter=Q(
                            status="UTILIZED"
                        ),
                        distinct=True,
                    ),
                    returned=Count(
                        "id",
                        filter=Q(
                            status="RETURNED"
                        ),
                        distinct=True,
                    ),
                )
                .order_by(
                    "-batches",
                    "chemical__name",
                )
            )
        except FieldError:
            return []

        output = []

        for row in rows:
            evaluated = (
                row["passed"]
                + row["failed"]
            )

            output.append(
                {
                    "chemical_id": row["chemical_id"],
                    "name": (
                        row["chemical__name"]
                        or "Unspecified"
                    ),
                    "code": row["chemical__code"],
                    "batches": row["batches"],
                    "results": row["results"],
                    "passed": row["passed"],
                    "failed": row["failed"],
                    "na": row["na"],
                    "received": row["received"],
                    "approved": row["approved"],
                    "rejected": row["rejected"],
                    "utilized": row["utilized"],
                    "returned": row["returned"],
                    "pass_rate": round(
                        row["passed"] / evaluated * 100
                        if evaluated
                        else 0,
                        2,
                    ),
                    "failure_rate": round(
                        row["failed"] / evaluated * 100
                        if evaluated
                        else 0,
                        2,
                    ),
                }
            )

        return output

    def get_user_workload(self, processes):
        workload = {}

        for process in processes:
            users = []

            analyst = getattr(
                process,
                "assigned_analyst",
                None,
            )

            if analyst:
                users.append(analyst)

            users.extend(
                self._process_assigned_analysts(process)
            )

            seen = set()

            for user in users:
                user_id = getattr(
                    user,
                    "pk",
                    None,
                )

                if not user_id or user_id in seen:
                    continue

                seen.add(user_id)

                self._add_workload_user(
                    workload,
                    user,
                    process,
                )

        output = list(workload.values())

        for item in output:
            item["active_rate"] = round(
                item["active"] / item["total"] * 100
                if item["total"]
                else 0,
                2,
            )

            item["completion_rate"] = round(
                item["completed"] / item["total"] * 100
                if item["total"]
                else 0,
                2,
            )

        output.sort(
            key=lambda item: (
                -item["active"],
                -item["total"],
                item["username"],
            )
        )

        return output

    def _add_workload_user(
        self,
        workload,
        user,
        process,
    ):
        user_id = getattr(user, "pk", None)

        if not user_id:
            return

        if user_id not in workload:
            workload[user_id] = {
                "user_id": user_id,
                "username": (
                    getattr(user, "username", None)
                    or getattr(user, "get_username", lambda: "")()
                    or "Unknown"
                ),
                "total": 0,
                "active": 0,
                "analysis": 0,
                "retest": 0,
                "qa": 0,
                "completed": 0,
                "approved": 0,
                "rejected": 0,
            }

        item = workload[user_id]

        item["total"] += 1

        status = self._normalize_status(
            getattr(process, "status", None)
        )

        if status in ACTIVE_PROCESS_STATUSES:
            item["active"] += 1

        if status == "ANALYSIS":
            item["analysis"] += 1

        elif status == "RETEST":
            item["retest"] += 1

        elif status == "QA":
            item["qa"] += 1

        elif status == "COMPLETED":
            item["completed"] += 1

        elif status == "APPROVED":
            item["approved"] += 1

        elif status == "REJECTED":
            item["rejected"] += 1

    def get_workflow_nodes(self, queue_counts, processes):
        status_counts = self.get_process_counts(processes)
        permissions = self.get_permissions()

        nodes = []

        for key, definition in FLOW_NODE_DEFINITIONS.items():
            queue_key = definition.get("queue")
            permission = definition.get("permission")

            permission_key = self._permission_key(
                permission
            )

            allowed = (
                True
                if not permission_key
                else permissions.get(permission_key, False)
            )

            queue_count = (
                queue_counts.get(queue_key, 0)
                if queue_key
                else 0
            )

            nodes.append(
                {
                    "id": key,
                    "label": definition["label"],
                    "status": definition["status"],
                    "queue": queue_key,
                    "count": queue_count,
                    "status_count": status_counts.get(
                        definition["status"],
                        0,
                    ),
                    "allowed": allowed,
                    "permission": permission,
                }
            )

        return nodes

    def get_stage_metrics(
        self,
        processes,
        batches,
        requests,
        coas,
        queue_counts,
    ):
        stages = [
            "received",
            "request",
            "checklist",
            "assignment_pending",
            "assignment_overdue",
            "analysis_ready",
            "analysis",
            "retest",
            "qa",
            "approval",
            "coa",
            "coa_approval",
            "disposition",
            "utilization",
            "return",
            "rejected",
            "completed",
        ]

        active_keys = {
            "received",
            "request",
            "checklist",
            "assignment_pending",
            "assignment_overdue",
            "analysis_ready",
            "analysis",
            "retest",
            "qa",
            "approval",
            "coa",
            "coa_approval",
            "disposition",
        }

        total_active = sum(
            queue_counts.get(key, 0)
            for key in active_keys
        )

        output = []

        for key in stages:
            count = queue_counts.get(key, 0)

            output.append(
                {
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "count": count,
                    "share_of_active": round(
                        count / total_active * 100
                        if total_active
                        else 0,
                        2,
                    ),
                    "active": key in active_keys,
                }
            )

        largest_queue = max(
            output,
            key=lambda item: item["count"],
            default=None,
        )

        return {
            "stages": output,
            "total_active": total_active,
            "largest_queue": largest_queue,
            "coa": len(coas),
            "sla_overdue": queue_counts.get(
                "overdue",
                0,
            ),
            "due_soon": queue_counts.get(
                "due_soon",
                0,
            ),
        }

    def get_operational_summary(
        self,
        processes,
        batches,
        requests,
        results,
        checklists,
        coas,
        queue_counts,
    ):
        process_counts = self.get_process_counts(
            processes
        )

        active_processes = sum(
            process_counts.get(status, 0)
            for status in ACTIVE_PROCESS_STATUSES
        )

        terminal_processes = sum(
            process_counts.get(status, 0)
            for status in TERMINAL_PROCESS_STATUSES
        )

        completed_processes = process_counts.get(
            "COMPLETED",
            0,
        )

        completed_batches = sum(
            1
            for batch in batches
            if self._normalize_status(
                getattr(batch, "status", None)
            ) in {
                "UTILIZED",
                "RETURNED",
            }
        )

        return {
            "process_status_counts": dict(
                process_counts
            ),
            "active_processes": active_processes,
            "terminal_processes": terminal_processes,
            "completed_processes": completed_processes,
            "completed_batches": completed_batches,
            "requests": len(requests),
            "results": len(results),
            "checklists": len(checklists),
            "coas": len(coas),
            "queue_pressure": queue_counts.get(
                "active_total",
                0,
            ),
            "exceptions": queue_counts.get(
                "exception_total",
                0,
            ),
        }

    def get_performance_summary(
        self,
        analyst_performance,
        supplier_performance,
        chemical_performance,
        workload,
    ):
        total_results = sum(
            item["total"]
            for item in analyst_performance
        )

        passed_results = sum(
            item["passed"]
            for item in analyst_performance
        )

        total_supplier_batches = sum(
            item["batches"]
            for item in supplier_performance
        )

        total_chemical_batches = sum(
            item["batches"]
            for item in chemical_performance
        )

        return {
            "analysts": {
                "users": len(analyst_performance),
                "results": total_results,
                "passed": passed_results,
                "pass_rate": round(
                    passed_results / total_results * 100
                    if total_results
                    else 0,
                    2,
                ),
            },
            "suppliers": {
                "suppliers": len(
                    supplier_performance
                ),
                "batches": total_supplier_batches,
            },
            "chemicals": {
                "chemicals": len(
                    chemical_performance
                ),
                "batches": total_chemical_batches,
            },
            "workforce": {
                "assigned_users": len(workload),
                "active_assignments": sum(
                    item["active"]
                    for item in workload
                ),
                "total_assignments": sum(
                    item["total"]
                    for item in workload
                ),
            },
        }

    def get_quality_summary(
        self,
        quality,
        coa_metrics,
        checklist_metrics,
    ):
        return {
            "analytical": {
                "passed": quality["passed"],
                "failed": quality["failed"],
                "conformance_rate": quality[
                    "pass_rate"
                ],
                "pending": quality["pending"],
            },
            "coa": {
                "approved": coa_metrics["approved"],
                "verified": coa_metrics["verified"],
                "approval_rate": coa_metrics[
                    "approval_rate"
                ],
                "verification_rate": coa_metrics[
                    "verification_rate"
                ],
            },
            "checklist": {
                "completed": checklist_metrics[
                    "completed"
                ],
                "expired": checklist_metrics[
                    "expired"
                ],
                "completion_rate": checklist_metrics[
                    "completion_rate"
                ],
            },
        }

    def get_risk_summary(self, risk_register):
        severity = Counter(
            item.get("severity", "MEDIUM")
            for item in risk_register
        )

        return {
            "severity": dict(severity),
            "total": len(risk_register),
            "critical": severity.get("CRITICAL", 0),
            "high": severity.get("HIGH", 0),
            "medium": severity.get("MEDIUM", 0),
            "low": severity.get("LOW", 0),
            "top": risk_register[:10],
        }

    def get_workflow_aging(self, processes):
        now = timezone.now()

        buckets = {
            "under_3h": 0,
            "3_to_9h": 0,
            "9_to_24h": 0,
            "1_to_3d": 0,
            "over_3d": 0,
        }

        records = []

        for process in processes:
            status = self._normalize_status(
                getattr(process, "status", None)
            )

            if status not in ACTIVE_PROCESS_STATUSES:
                continue

            started = (
                getattr(
                    process,
                    "analysis_started_at",
                    None,
                )
                or getattr(
                    process,
                    "created_at",
                    None,
                )
            )

            if not started:
                continue

            started = self._aware(started)

            age_hours = max(
                0,
                (
                    now - started
                ).total_seconds() / 3600,
            )

            if age_hours < 3:
                bucket = "under_3h"
            elif age_hours < 9:
                bucket = "3_to_9h"
            elif age_hours < 24:
                bucket = "9_to_24h"
            elif age_hours < 72:
                bucket = "1_to_3d"
            else:
                bucket = "over_3d"

            buckets[bucket] += 1

            request = getattr(
                process,
                "analysis_request",
                None,
            )

            deadline = (
                self._request_deadline(request)
                if request
                else None
            )

            records.append(
                {
                    "process_id": getattr(
                        process,
                        "pk",
                        None,
                    ),
                    "batch_id": getattr(
                        process,
                        "batch_id",
                        None,
                    ),
                    "status": status,
                    "age_hours": round(
                        age_hours,
                        2,
                    ),
                    "deadline": self._iso(
                        deadline
                    ),
                    "overdue": bool(
                        deadline
                        and deadline <= now
                    ),
                }
            )

        records.sort(
            key=lambda item: -item["age_hours"]
        )

        return {
            "buckets": buckets,
            "records": records[:100],
        }

    def get_result_distribution(self, results):
        counts = self.get_result_counts(results)

        preferred = [
            "PASS",
            "PASSED",
            "FAIL",
            "FAILED",
            "NA",
            "N/A",
            "NOT_APPLICABLE",
            "PENDING",
            "INCOMPLETE",
        ]

        labels = []
        values = []

        for status in preferred:
            value = counts.get(status, 0)

            if value:
                labels.append(status)
                values.append(value)

        for status, value in sorted(counts.items()):
            if status in preferred:
                continue

            labels.append(status or "UNSPECIFIED")
            values.append(value)

        return {
            "labels": labels,
            "values": values,
            "counts": dict(counts),
        }

    def get_lifecycle_funnel(
        self,
        batches,
        requests,
        processes,
        coas,
        process_by_batch,
    ):
        process_counts = self.get_process_counts(
            processes
        )

        batch_counts = self.get_batch_counts(
            batches
        )

        latest_processes = list(
            process_by_batch.values()
        )

        latest_status_counts = self.get_process_counts(
            latest_processes
        )

        return {
            "batches": len(batches),
            "received": batch_counts.get(
                "RECEIVED",
                0,
            ),
            "requests": len(requests),
            "checklist": latest_status_counts.get(
                "CHECKLIST",
                0,
            ),
            "analysis": latest_status_counts.get(
                "ANALYSIS",
                0,
            ),
            "retest": latest_status_counts.get(
                "RETEST",
                0,
            ),
            "qa": latest_status_counts.get(
                "QA",
                0,
            ),
            "approved": batch_counts.get(
                "APPROVED",
                0,
            ),
            "coa": len(coas),
            "utilized": batch_counts.get(
                "UTILIZED",
                0,
            ),
            "returned": batch_counts.get(
                "RETURNED",
                0,
            ),
            "rejected": batch_counts.get(
                "REJECTED",
                0,
            ),
            "completed": latest_status_counts.get(
                "COMPLETED",
                0,
            ),
            "process_status_counts": dict(
                process_counts
            ),
            "latest_process_status_counts": dict(
                latest_status_counts
            ),
            "batch_status_counts": dict(
                batch_counts
            ),
        }

    def get_throughput_trends(
        self,
        batches,
        processes,
        results,
    ):
        today = timezone.localdate()
        start_date = today - timedelta(days=29)

        rows = []

        for offset in range(30):
            current_date = start_date + timedelta(
                days=offset
            )

            batch_created = sum(
                1
                for batch in batches
                if self._date_value(
                    getattr(
                        batch,
                        "created_at",
                        None,
                    )
                )
                == current_date
            )

            batch_received = sum(
                1
                for batch in batches
                if self._date_value(
                    getattr(
                        batch,
                        "received_at",
                        None,
                    )
                )
                == current_date
            )

            process_created = sum(
                1
                for process in processes
                if self._date_value(
                    getattr(
                        process,
                        "created_at",
                        None,
                    )
                )
                == current_date
            )

            process_completed = sum(
                1
                for process in processes
                if self._date_value(
                    getattr(
                        process,
                        "completed_at",
                        None,
                    )
                )
                == current_date
            )

            results_recorded = sum(
                1
                for result in results
                if self._date_value(
                    getattr(
                        result,
                        "tested_at",
                        None,
                    )
                )
                == current_date
            )

            rows.append(
                {
                    "date": current_date.isoformat(),
                    "batch_created": batch_created,
                    "batch_received": batch_received,
                    "process_created": process_created,
                    "process_completed": process_completed,
                    "results_recorded": results_recorded,
                }
            )

        return rows

    def get_risk_register(
        self,
        batches,
        requests,
        results,
        processes,
        checklists,
        coas,
        process_by_batch,
    ):
        now = timezone.now()
        risks = []

        def add_risk(
            severity,
            category,
            title,
            description,
            obj=None,
            timestamp=None,
        ):
            risks.append(
                {
                    "severity": severity,
                    "category": category,
                    "title": title,
                    "description": description,
                    "object_id": getattr(
                        obj,
                        "pk",
                        None,
                    ),
                    "batch_id": getattr(
                        obj,
                        "batch_id",
                        None,
                    ),
                    "timestamp": self._iso(
                        timestamp
                        or getattr(
                            obj,
                            "updated_at",
                            None,
                        )
                        or getattr(
                            obj,
                            "created_at",
                            None,
                        )
                    ),
                }
            )

        for request in requests:
            status = self._normalize_status(
                getattr(request, "status", None)
            )

            deadline = self._request_deadline(
                request
            )

            if (
                deadline
                and deadline <= now
                and status != "COMPLETED"
            ):
                add_risk(
                    "CRITICAL",
                    "SLA_BREACH",
                    "Analysis request overdue",
                    "The analysis request has exceeded its applicable SLA deadline.",
                    request,
                    deadline,
                )

            batch_id = getattr(
                request,
                "batch_id",
                None,
            )

            if (
                batch_id
                and batch_id not in process_by_batch
                and status not in {"COMPLETED"}
            ):
                add_risk(
                    "CRITICAL",
                    "PROCESS_MISSING",
                    "Analysis process missing",
                    "The active analysis request does not have a corresponding chemical analysis process.",
                    request,
                )

            if (
                status in {"PENDING", "IN_PROGRESS"}
                and not self._request_has_assigned_analysts(
                    request
                )
                and self._request_assignment_overdue(
                    request
                )
            ):
                add_risk(
                    "HIGH",
                    "ANALYST_ASSIGNMENT_OVERDUE",
                    "Analyst assignment overdue",
                    "No analyst has been assigned within the 30-minute assignment window.",
                    request,
                    self._request_assignment_deadline(
                        request
                    ),
                )

        for result in results:
            status = self._normalize_result_status(
                getattr(result, "status", None)
            )

            if status in FAIL_STATUSES:
                add_risk(
                    "HIGH",
                    "FAILED_RESULT",
                    "Failed analytical result",
                    "A recorded analytical result is marked as failed.",
                    result,
                    getattr(
                        result,
                        "tested_at",
                        None,
                    ),
                )

            if not getattr(result, "analyst_id", None):
                add_risk(
                    "MEDIUM",
                    "RESULT_WITHOUT_ANALYST",
                    "Result without analyst",
                    "The analytical result does not identify an analyst.",
                    result,
                    getattr(
                        result,
                        "tested_at",
                        None,
                    ),
                )

        coa_by_batch = {}

        for coa in coas:
            batch_id = getattr(
                coa,
                "batch_id",
                None,
            )

            if batch_id:
                coa_by_batch.setdefault(
                    batch_id,
                    [],
                ).append(coa)

        for process in processes:
            status = self._normalize_status(
                getattr(process, "status", None)
            )

            batch_id = getattr(
                process,
                "batch_id",
                None,
            )

            if status == "APPROVED":
                batch_coas = coa_by_batch.get(
                    batch_id,
                    [],
                )

                if not batch_coas:
                    add_risk(
                        "HIGH",
                        "MISSING_COA",
                        "Approved process without CoA",
                        "The analysis process is approved but no Certificate of Analysis is associated with the batch.",
                        process,
                    )
                elif not any(
                    self._coa_is_approved(coa)
                    for coa in batch_coas
                ):
                    add_risk(
                        "HIGH",
                        "COA_NOT_APPROVED",
                        "CoA not approved",
                        "A Certificate of Analysis exists but has not reached an approved state.",
                        process,
                    )

            if (
                status in {"ANALYSIS", "RETEST"}
                and not self._process_has_assigned_analysts(
                    process
                )
            ):
                category = (
                    "ANALYST_NOT_ASSIGNED"
                    if status == "ANALYSIS"
                    else "RETEST_ANALYST_NOT_ASSIGNED"
                )

                add_risk(
                    "HIGH",
                    category,
                    "Analyst not assigned",
                    "The active analytical stage has no assigned analyst.",
                    process,
                )

            started = (
                getattr(
                    process,
                    "analysis_started_at",
                    None,
                )
                or getattr(
                    process,
                    "created_at",
                    None,
                )
            )

            if (
                status in ACTIVE_PROCESS_STATUSES
                and started
                and (
                    now - self._aware(started)
                ) > timedelta(hours=24)
            ):
                add_risk(
                    "HIGH",
                    "STALE_PROCESS",
                    "Stale analysis process",
                    "The active process has remained open for more than 24 hours.",
                    process,
                    started,
                )

        for checklist in checklists:
            if self._checklist_expired_incomplete(
                checklist
            ):
                add_risk(
                    "HIGH",
                    "EXPIRED_CHECKLIST",
                    "Expired receiving checklist",
                    "The receiving checklist is incomplete beyond its applicable deadline.",
                    checklist,
                )

        weights = {
            "CRITICAL": 4,
            "HIGH": 3,
            "MEDIUM": 2,
            "LOW": 1,
        }

        risks.sort(
            key=lambda item: (
                -weights.get(
                    item["severity"],
                    0,
                ),
                item["timestamp"] or "",
            ),
            reverse=False,
        )

        risks.sort(
            key=lambda item: (
                -weights.get(
                    item["severity"],
                    0,
                ),
                item["timestamp"] or "",
            ),
            reverse=False,
        )

        return risks[:100]

    def get_attention_items(
        self,
        queue_counts,
        sla,
        quality,
        coa_metrics,
        checklist_metrics,
        data_quality,
    ):
        definitions = [
            (
                "overdue",
                "Overdue SLA items",
                "CRITICAL",
                "ca:overdue-analysis",
            ),
            (
                "assignment_overdue",
                "Analyst assignment overdue",
                "CRITICAL",
                "ca:pending-analysis",
            ),
            (
                "failed_results",
                "Failed analytical results",
                "HIGH",
                "ca:result-list",
            ),
            (
                "retest",
                "Retest queue",
                "HIGH",
                "ca:process-list",
            ),
            (
                "qa",
                "QA review queue",
                "HIGH",
                "ca:process-list",
            ),
            (
                "approval",
                "Approval queue",
                "HIGH",
                "ca:process-list",
            ),
            (
                "coa",
                "CoA generation queue",
                "HIGH",
                "ca:coa-list",
            ),
            (
                "coa_approval",
                "CoA approval queue",
                "HIGH",
                "ca:coa-list",
            ),
            (
                "coa_integrity",
                "CoA integrity exceptions",
                "CRITICAL",
                "ca:coa-list",
            ),
            (
                "expired_checklists",
                "Expired incomplete checklists",
                "HIGH",
                "ca:process-list",
            ),
            (
                "data_quality",
                "Data quality exceptions",
                "MEDIUM",
                "ca:process-list",
            ),
        ]

        values = {
            "overdue": sla.get("overdue", 0),
            "assignment_overdue": queue_counts.get(
                "assignment_overdue",
                0,
            ),
            "failed_results": quality.get(
                "failed",
                0,
            ),
            "retest": queue_counts.get(
                "retest",
                0,
            ),
            "qa": queue_counts.get(
                "qa",
                0,
            ),
            "approval": queue_counts.get(
                "approval",
                0,
            ),
            "coa": queue_counts.get(
                "coa",
                0,
            ),
            "coa_approval": queue_counts.get(
                "coa_approval",
                0,
            ),
            "coa_integrity": coa_metrics.get(
                "failed_integrity",
                0,
            ),
            "expired_checklists": checklist_metrics.get(
                "incomplete_expired",
                0,
            ),
            "data_quality": data_quality.get(
                "total",
                0,
            ),
        }

        output = []

        for (
            key,
            label,
            severity,
            url_name,
        ) in definitions:
            count = values.get(key, 0)

            if not count:
                continue

            output.append(
                {
                    "key": key,
                    "label": label,
                    "count": count,
                    "severity": severity,
                    "url": self.safe_reverse(
                        url_name
                    ),
                }
            )

        return output

    def get_data_quality_metrics(
        self,
        batches,
        requests,
        results,
        processes,
        checklists,
        coas,
        process_by_batch,
    ):
        missing_plant = sum(
            1
            for batch in batches
            if not getattr(
                batch,
                "treatment_plant_id",
                None,
            )
        )

        missing_process = sum(
            1
            for request in requests
            if (
                self._normalize_status(
                    getattr(request, "status", None)
                )
                != "COMPLETED"
                and getattr(
                    request,
                    "batch_id",
                    None,
                )
                not in process_by_batch
            )
        )

        result_without_analyst = sum(
            1
            for result in results
            if not getattr(
                result,
                "analyst_id",
                None,
            )
        )

        incomplete_checklists = sum(
            1
            for checklist in checklists
            if not self._checklist_is_complete(
                checklist
            )
        )

        incomplete_expired_checklists = sum(
            1
            for checklist in checklists
            if self._checklist_expired_incomplete(
                checklist
            )
        )

        missing_coa = sum(
            1
            for process in processes
            if (
                self._normalize_status(
                    getattr(process, "status", None)
                ) == "APPROVED"
                and not self._process_has_coa(process)
            )
        )

        active_without_analyst = sum(
            1
            for process in processes
            if (
                self._normalize_status(
                    getattr(process, "status", None)
                ) in {
                    "ANALYSIS",
                    "RETEST",
                }
                and not self._process_has_assigned_analysts(
                    process
                )
            )
        )

        assignment_overdue = sum(
            1
            for request in requests
            if (
                self._normalize_status(
                    getattr(request, "status", None)
                )
                in {"PENDING", "IN_PROGRESS"}
                and not self._request_has_assigned_analysts(
                    request
                )
                and self._request_assignment_overdue(
                    request
                )
            )
        )

        total = (
            missing_plant
            + missing_process
            + result_without_analyst
            + incomplete_expired_checklists
            + missing_coa
            + active_without_analyst
            + assignment_overdue
        )

        return {
            "missing_plant": missing_plant,
            "missing_process": missing_process,
            "result_without_analyst": result_without_analyst,
            "incomplete_checklists": incomplete_checklists,
            "incomplete_expired_checklists": incomplete_expired_checklists,
            "missing_coa": missing_coa,
            "active_without_analyst": active_without_analyst,
            "assignment_overdue": assignment_overdue,
            "total": total,
        }

    def get_workflow_health(
        self,
        queue_counts,
        sla,
        quality,
        data_quality,
        coa_metrics,
    ):
        critical = (
            sla.get("overdue", 0)
            + queue_counts.get(
                "assignment_overdue",
                0,
            )
            + quality.get(
                "failed",
                0,
            )
            + coa_metrics.get(
                "failed_integrity",
                0,
            )
            + data_quality.get(
                "missing_process",
                0,
            )
            + data_quality.get(
                "missing_coa",
                0,
            )
            + data_quality.get(
                "incomplete_expired_checklists",
                0,
            )
        )

        active = queue_counts.get(
            "active_total",
            0,
        )

        if critical:
            state = "ATTENTION"
        elif active:
            state = "ACTIVE"
        else:
            state = "IDLE"

        return {
            "state": state,
            "critical": critical,
            "active": active,
            "normal_workflow_queues": (
                queue_counts.get(
                    "qa",
                    0,
                )
                + queue_counts.get(
                    "approval",
                    0,
                )
                + queue_counts.get(
                    "coa",
                    0,
                )
                + queue_counts.get(
                    "coa_approval",
                    0,
                )
            ),
        }

    def get_recent_activity(
        self,
        batches,
        requests,
        processes,
        results,
        coas,
    ):
        events = []

        for batch in batches:
            status = self._normalize_status(
                getattr(batch, "status", None)
            )

            event_label = {
                "RECEIVED": "Chemical batch received",
                "ANALYSED": "Chemical batch analysed",
                "APPROVED": "Chemical batch approved",
                "REJECTED": "Chemical batch rejected",
                "UTILIZED": "Chemical batch utilized",
                "RETURNED": "Chemical batch returned",
            }.get(
                status,
                "Chemical batch updated",
            )

            events.append(
                {
                    "type": "batch",
                    "event": event_label,
                    "object_id": getattr(
                        batch,
                        "pk",
                        None,
                    ),
                    "batch_id": getattr(
                        batch,
                        "pk",
                        None,
                    ),
                    "status": status,
                    "timestamp": self._iso(
                        getattr(
                            batch,
                            "updated_at",
                            None,
                        )
                        or getattr(
                            batch,
                            "created_at",
                            None,
                        )
                    ),
                }
            )

        for request in requests:
            events.append(
                {
                    "type": "request",
                    "event": "Analysis request updated",
                    "object_id": getattr(
                        request,
                        "pk",
                        None,
                    ),
                    "batch_id": getattr(
                        request,
                        "batch_id",
                        None,
                    ),
                    "status": self._normalize_status(
                        getattr(
                            request,
                            "status",
                            None,
                        )
                    ),
                    "timestamp": self._iso(
                        getattr(
                            request,
                            "updated_at",
                            None,
                        )
                        or getattr(
                            request,
                            "created_at",
                            None,
                        )
                    ),
                }
            )

        for process in processes:
            status = self._normalize_status(
                getattr(process, "status", None)
            )

            label = {
                "CREATED": "Analysis process registered",
                "RECEIVED": "Batch received",
                "REQUESTED": "Analysis request created",
                "CHECKLIST": "Receiving checklist stage",
                "ANALYSIS": "Chemical analysis in progress",
                "RETEST": "Chemical retest in progress",
                "QA": "QA review in progress",
                "APPROVED": "Analysis approved",
                "REJECTED": "Analysis rejected",
                "UTILIZED": "Batch utilized",
                "RETURNED": "Batch returned",
                "COMPLETED": "Analysis workflow completed",
            }.get(
                status,
                "Analysis process updated",
            )

            events.append(
                {
                    "type": "process",
                    "event": label,
                    "object_id": getattr(
                        process,
                        "pk",
                        None,
                    ),
                    "batch_id": getattr(
                        process,
                        "batch_id",
                        None,
                    ),
                    "status": status,
                    "timestamp": self._iso(
                        getattr(
                            process,
                            "updated_at",
                            None,
                        )
                        or getattr(
                            process,
                            "created_at",
                            None,
                        )
                    ),
                }
            )

        for result in results:
            events.append(
                {
                    "type": "result",
                    "event": "Analytical result recorded",
                    "object_id": getattr(
                        result,
                        "pk",
                        None,
                    ),
                    "batch_id": getattr(
                        result,
                        "batch_id",
                        None,
                    ),
                    "status": self._normalize_result_status(
                        getattr(
                            result,
                            "status",
                            None,
                        )
                    ),
                    "timestamp": self._iso(
                        getattr(
                            result,
                            "tested_at",
                            None,
                        )
                        or getattr(
                            result,
                            "created_at",
                            None,
                        )
                    ),
                }
            )

        for coa in coas:
            events.append(
                {
                    "type": "coa",
                    "event": "Certificate of Analysis updated",
                    "object_id": getattr(
                        coa,
                        "pk",
                        None,
                    ),
                    "batch_id": getattr(
                        coa,
                        "batch_id",
                        None,
                    ),
                    "status": self._normalize_status(
                        getattr(
                            coa,
                            "status",
                            None,
                        )
                    ),
                    "timestamp": self._iso(
                        getattr(
                            coa,
                            "updated_at",
                            None,
                        )
                        or getattr(
                            coa,
                            "created_at",
                            None,
                        )
                    ),
                }
            )

        events.sort(
            key=lambda item: item.get(
                "timestamp"
            ) or "",
            reverse=True,
        )

        return events[:100]

    def get_my_tasks(
        self,
        processes,
        requests,
    ):
        user = self.request.user
        user_id = getattr(user, "pk", None)
        now = timezone.now()

        tasks = []
        seen = set()

        for process in processes:
            process_id = getattr(
                process,
                "pk",
                None,
            )

            roles = []

            if getattr(
                process,
                "assigned_analyst_id",
                None,
            ) == user_id:
                roles.append("analyst")

            if getattr(
                process,
                "qa_officer_id",
                None,
            ) == user_id:
                roles.append("qa")

            if getattr(
                process,
                "approver_id",
                None,
            ) == user_id:
                roles.append("approver")

            request = getattr(
                process,
                "analysis_request",
                None,
            )

            if request:
                if any(
                    getattr(
                        analyst,
                        "pk",
                        None,
                    ) == user_id
                    for analyst in self._process_assigned_analysts(
                        process
                    )
                ):
                    roles.append("assigned_analyst")

            if not roles:
                continue

            deadline = (
                self._request_deadline(request)
                if request
                else None
            )

            task_key = (
                "process",
                process_id,
                tuple(sorted(set(roles))),
            )

            if task_key in seen:
                continue

            seen.add(task_key)

            tasks.append(
                {
                    "type": "process",
                    "process_id": process_id,
                    "batch_id": getattr(
                        process,
                        "batch_id",
                        None,
                    ),
                    "status": self._normalize_status(
                        getattr(
                            process,
                            "status",
                            None,
                        )
                    ),
                    "roles": sorted(set(roles)),
                    "deadline": self._iso(
                        deadline
                    ),
                    "overdue": bool(
                        deadline
                        and deadline <= now
                    ),
                }
            )

        for request in requests:
            if (
                getattr(
                    request,
                    "requested_by_id",
                    None,
                ) != user_id
            ):
                continue

            if self._request_has_assigned_analysts(
                request
            ):
                continue

            deadline = self._request_assignment_deadline(
                request
            )

            tasks.append(
                {
                    "type": "assignment",
                    "request_id": getattr(
                        request,
                        "pk",
                        None,
                    ),
                    "batch_id": getattr(
                        request,
                        "batch_id",
                        None,
                    ),
                    "status": self._normalize_status(
                        getattr(
                            request,
                            "status",
                            None,
                        )
                    ),
                    "roles": ["assignment"],
                    "deadline": self._iso(
                        deadline
                    ),
                    "overdue": bool(
                        deadline
                        and deadline <= now
                    ),
                }
            )

        tasks.sort(
            key=lambda item: (
                not item["overdue"],
                item["deadline"] or "",
            )
        )

        return tasks[:100]

    def get_viewflow_version(self):
        for package_name in (
            "django-viewflow",
            "viewflow",
        ):
            try:
                return package_version(
                    package_name
                )
            except PackageNotFoundError:
                continue

        return "unknown"

    def safe_reverse(
        self,
        viewname,
        kwargs=None,
        args=None,
        fallback=None,
    ):
        try:
            return reverse(
                viewname,
                kwargs=kwargs,
                args=args,
            )
        except (
            NoReverseMatch,
            TypeError,
            ValueError,
        ):
            return fallback

    def _resolve_first_url(
        self,
        candidates,
    ):
        for candidate in candidates:
            url = self.safe_reverse(
                candidate
            )

            if url:
                return url

        return None

    def _json_response(self):
        return JsonResponse(
            self._json_safe(
                self._dashboard_data()
            )
        )


    def _process_is_analysis_ready(
        self,
        process,
    ):
        explicit = getattr(
            process,
            "analysis_ready",
            None,
        )

        if explicit is not None:
            return bool(explicit)

        checklist = getattr(
            process,
            "latest_checklist",
            None,
        )

        if checklist is None:
            request = getattr(
                process,
                "analysis_request",
                None,
            )

            if request:
                checklist = getattr(
                    request,
                    "latest_checklist",
                    None,
                )

        if checklist is not None:
            if not self._checklist_is_complete(
                checklist
            ):
                return False
        else:
            if not getattr(
                process,
                "checklist_completed_at",
                None,
            ):
                return False

        return self._process_has_assigned_analysts(
            process
        )

    def _process_has_assigned_analysts(
        self,
        process,
    ):
        explicit = getattr(
            process,
            "has_assigned_analysts",
            None,
        )

        if explicit is not None:
            return bool(explicit)

        assigned_id = getattr(
            process,
            "assigned_analyst_id",
            None,
        )

        if assigned_id:
            return True

        return bool(
            self._process_assigned_analysts(
                process
            )
        )

    def _process_assigned_analysts(
        self,
        process,
    ):
        request = getattr(
            process,
            "analysis_request",
            None,
        )

        if not request:
            return []

        try:
            return list(
                request.assigned_analysts.all()
            )
        except (
            AttributeError,
            TypeError,
        ):
            return []

    def _request_has_assigned_analysts(
        self,
        request,
    ):
        explicit = getattr(
            request,
            "has_assigned_analysts",
            None,
        )

        if explicit is not None:
            return bool(explicit)

        try:
            return request.assigned_analysts.exists()
        except (
            AttributeError,
            TypeError,
        ):
            return bool(
                getattr(
                    request,
                    "assigned_analyst_id",
                    None,
                )
            )

    def _request_assignment_deadline(
        self,
        request,
    ):
        for field_name in (
            "assignment_deadline",
            "manual_assignment_deadline",
        ):
            value = getattr(
                request,
                field_name,
                None,
            )

            if value:
                return self._aware(value)

        for field_name in (
            "created_at",
            "requested_at",
        ):
            value = getattr(
                request,
                field_name,
                None,
            )

            if value:
                return (
                    self._aware(value)
                    + timedelta(minutes=30)
                )

        return None

    def _request_assignment_overdue(
        self,
        request,
    ):
        explicit = getattr(
            request,
            "assignment_overdue",
            None,
        )

        if explicit is not None:
            return bool(explicit)

        deadline = self._request_assignment_deadline(
            request
        )

        return bool(
            deadline
            and deadline <= timezone.now()
            and not self._request_has_assigned_analysts(
                request
            )
        )

    def _request_assignment_overdue_hours(
        self,
        request,
    ):
        deadline = self._request_assignment_deadline(
            request
        )

        if not deadline:
            return 0

        return max(
            0,
            (
                timezone.now() - deadline
            ).total_seconds() / 3600,
        )

    def _request_deadline(self, request):
        if not request:
            return None

        for field_name in (
            "deadline",
            "analysis_deadline",
            "due_at",
            "due_date",
            "sla_deadline",
        ):
            value = getattr(
                request,
                field_name,
                None,
            )

            if value:
                if isinstance(
                    value,
                    datetime,
                ):
                    return self._aware(value)

                return value

        return None

    def _process_requires_approval(
        self,
        process,
    ):
        for field_name in (
            "approval_required",
            "requires_approval",
            "ready_for_approval",
            "analysis_approved",
        ):
            value = getattr(
                process,
                field_name,
                None,
            )

            if value is not None:
                if field_name == "analysis_approved":
                    return not bool(value)

                return bool(value)

        return False

    def _process_has_coa(
        self,
        process,
    ):
        batch_id = getattr(
            process,
            "batch_id",
            None,
        )

        if not batch_id:
            return False

        try:
            return ChemicalCoA.objects.filter(
                batch_id=batch_id
            ).exists()
        except Exception:
            return False

    def _process_has_approved_coa(
        self,
        process,
    ):
        batch_id = getattr(
            process,
            "batch_id",
            None,
        )

        if not batch_id:
            return False

        try:
            coas = ChemicalCoA.objects.filter(
                batch_id=batch_id
            )

            return any(
                self._coa_is_approved(coa)
                for coa in coas
            )
        except Exception:
            return False

    def _coa_is_approved(
        self,
        coa,
    ):
        for field_name in (
            "is_approved",
            "approved",
        ):
            value = getattr(
                coa,
                field_name,
                None,
            )

            if value is not None:
                return bool(value)

        status = self._normalize_status(
            getattr(
                coa,
                "status",
                None,
            )
        )

        return status in {
            "APPROVED",
            "VERIFIED",
        }

    def _coa_assets_available(
        self,
        coa,
    ):
        pdf = getattr(
            coa,
            "pdf_file",
            None,
        )

        qr = getattr(
            coa,
            "qr_code",
            None,
        )

        if pdf and qr:
            return True

        assets = getattr(
            coa,
            "assets",
            None,
        )

        if isinstance(
            assets,
            dict,
        ):
            return bool(
                assets.get("pdf")
                and assets.get("qr")
            )

        return False

    def _checklist_is_complete(
        self,
        checklist,
    ):
        for field_name in (
            "completed",
            "is_completed",
            "checklist_completed",
        ):
            value = getattr(
                checklist,
                field_name,
                None,
            )

            if value is not None:
                return bool(value)

        status = self._normalize_status(
            getattr(
                checklist,
                "status",
                None,
            )
        )

        if status in {
            "COMPLETED",
            "COMPLETE",
            "DONE",
        }:
            return True

        return bool(
            getattr(
                checklist,
                "completed_at",
                None,
            )
        )

    def _checklist_is_expired(
        self,
        checklist,
    ):
        explicit = getattr(
            checklist,
            "expired",
            None,
        )

        if explicit is not None:
            return bool(explicit)

        explicit = getattr(
            checklist,
            "is_expired",
            None,
        )

        if explicit is not None:
            return bool(explicit)

        deadline = None

        for field_name in (
            "deadline",
            "due_at",
            "expires_at",
        ):
            value = getattr(
                checklist,
                field_name,
                None,
            )

            if value:
                deadline = self._aware(value)
                break

        if not deadline:
            request = getattr(
                checklist,
                "chemical_analysis_request",
                None,
            )

            deadline = (
                self._request_deadline(request)
                if request
                else None
            )

        return bool(
            deadline
            and deadline <= timezone.now()
        )

    def _checklist_expired_incomplete(
        self,
        checklist,
    ):
        return (
            not self._checklist_is_complete(
                checklist
            )
            and self._checklist_is_expired(
                checklist
            )
        )

    def _permission_key(
        self,
        permission,
    ):
        if not permission:
            return None

        for key, value in CHEMICAL_PERMISSIONS.items():
            if value == permission:
                return key

        return None

    def _is_superuser(self):
        """Delegate to CaWanjalaMixin.is_ca_superuser (which uses SuperUserEngine)."""
        return self.is_ca_superuser()

    def _user_plant_id(self):
        """Delegate to CaWanjalaMixin.get_scope_plant_id."""
        return self.get_scope_plant_id()

    def _require_plant(self):
        """Delegate to CaWanjalaMixin.ensure_user_has_plant."""
        self.ensure_user_has_plant()

    def _serialize_inputs(self, inputs):
        output = []

        for item in inputs:
            result = getattr(
                item,
                "test_result",
                None,
            )

            parameter = getattr(
                result,
                "parameter",
                None,
            ) if result else None

            output.append(
                {
                    "id": getattr(
                        item,
                        "pk",
                        None,
                    ),
                    "test_result_id": getattr(
                        item,
                        "test_result_id",
                        None,
                    ),
                    "batch_id": getattr(
                        result,
                        "batch_id",
                        None,
                    ),
                    "parameter_id": getattr(
                        result,
                        "parameter_id",
                        None,
                    ) if result else None,
                    "parameter": (
                        getattr(
                            parameter,
                            "name",
                            None,
                        )
                        if parameter
                        else None
                    ),
                    "value": getattr(
                        item,
                        "value",
                        None,
                    ),
                    "unit": getattr(
                        item,
                        "unit",
                        None,
                    ),
                    "created_at": self._iso(
                        getattr(
                            item,
                            "created_at",
                            None,
                        )
                    ),
                }
            )

        return output[:500]

    def _normalize_status(
        self,
        value,
    ):
        if value is None:
            return ""

        return str(value).strip().upper()

    def _normalize_result_status(
        self,
        value,
    ):
        if value is None:
            return None

        value = str(value).strip().upper()

        return value or None

    def _risk(
        self,
        severity,
        category,
        title,
        description,
        obj=None,
        timestamp=None,
    ):
        return {
            "severity": severity,
            "category": category,
            "title": title,
            "description": description,
            "object_id": getattr(
                obj,
                "pk",
                None,
            ),
            "batch_id": getattr(
                obj,
                "batch_id",
                None,
            ),
            "timestamp": self._iso(
                timestamp
                or getattr(
                    obj,
                    "updated_at",
                    None,
                )
                or getattr(
                    obj,
                    "created_at",
                    None,
                )
            ),
        }

    def _risk_weight(
        self,
        severity,
    ):
        return {
            "CRITICAL": 4,
            "HIGH": 3,
            "MEDIUM": 2,
            "LOW": 1,
        }.get(
            severity,
            0,
        )

    def _hours_since(
        self,
        value,
    ):
        if not value:
            return 0

        value = self._aware(value)

        return round(
            max(
                0,
                (
                    timezone.now() - value
                ).total_seconds()
                / 3600,
            ),
            2,
        )

    def _aware(
        self,
        value,
    ):
        if value is None:
            return None

        if not isinstance(
            value,
            datetime,
        ):
            return value

        if timezone.is_naive(value):
            return timezone.make_aware(
                value,
                timezone.get_current_timezone(),
            )

        return value

    def _timestamp(
        self,
        value,
    ):
        if value is None:
            return datetime.min.replace(
                tzinfo=dt_timezone.utc
            )

        if isinstance(
            value,
            datetime,
        ):
            value = self._aware(value)

            if value.tzinfo is None:
                value = value.replace(
                    tzinfo=dt_timezone.utc
                )

            return value.astimezone(
                dt_timezone.utc
            )

        return datetime.min.replace(
            tzinfo=dt_timezone.utc
        )

    def _iso(
        self,
        value,
    ):
        if value is None:
            return None

        if isinstance(
            value,
            datetime,
        ):
            return self._aware(value).isoformat()

        if hasattr(
            value,
            "isoformat",
        ):
            return value.isoformat()

        return str(value)

    def _date_value(
        self,
        value,
    ):
        if value is None:
            return None

        if isinstance(
            value,
            datetime,
        ):
            return self._aware(value).date()

        if hasattr(
            value,
            "date",
        ):
            try:
                return value.date()
            except TypeError:
                pass

        return value

    def _number(
        self,
        value,
    ):
        if value is None:
            return None

        try:
            value = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return value

        if value.is_integer():
            return int(value)

        return round(
            value,
            6,
        )

    def _json_safe(
        self,
        value,
    ):
        if value is None:
            return None

        if isinstance(
            value,
            dict,
        ):
            return {
                str(key): self._json_safe(item)
                for key, item in value.items()
            }

        if isinstance(
            value,
            (list, tuple),
        ):
            return [
                self._json_safe(item)
                for item in value
            ]

        if isinstance(
            value,
            (datetime,),
        ):
            return self._iso(value)

        if hasattr(
            value,
            "isoformat",
        ) and not isinstance(
            value,
            str,
        ):
            try:
                return value.isoformat()
            except Exception:
                pass

        if hasattr(
            value,
            "url",
        ):
            try:
                return value.url
            except Exception:
                return None

        if hasattr(
            value,
            "name",
        ) and value.__class__.__module__.startswith(
            "django"
        ):
            try:
                return str(value)
            except Exception:
                return None

        if hasattr(
            value,
            "pk",
        ):
            return getattr(
                value,
                "pk",
                None,
            )

        try:
            import decimal

            if isinstance(
                value,
                decimal.Decimal,
            ):
                return float(value)
        except Exception:
            pass

        try:
            import uuid

            if isinstance(
                value,
                uuid.UUID,
            ):
                return str(value)
        except Exception:
            pass

        if isinstance(
            value,
            (str, int, float, bool),
        ):
            return value

        return str(value)