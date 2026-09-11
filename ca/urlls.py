
from __future__ import annotations

from django.urls import path

from viewflow.workflow.flow import FlowViewset

from .chemical_flow import ChemicalAnalysisFlow
from .views import (
    DashboardView,
    ChemicalBatchListView,
    ChemicalBatchDetailView,
    ChemicalBatchCreateView,
    ChemicalBatchUpdateView,
    ChemicalAnalysisRequestListView,
    ChemicalAnalysisRequestDetailView,
    ProcessListView,
    ProcessDetailView,
    ProcessJSONView,
    ProcessActionView,
    ChemicalAnalysisInputDetailView,
    RecalculateAnalysisInputView,
    ChemicalSpecificationListView,
    ResultListView,
    ResultDetailView,
    ChemicalCoAListView,
    ChemicalCoADetailView,
    RegenerateChemicalCoAView,
    VerifyChemicalCoAView,
    DownloadChemicalCoAView,
    ReopenChecklistView,
    ChecklistDetailView,
    ChecklistListView,
    ProcessStatisticsView,
    ProcessRefreshView,
    MyChemicalTasksView,
    OverdueAnalysisView,
    PendingAnalysisView,
    PendingQAReviewView,
    PendingApprovalView,
    TransitionBatchView,
    ChemicalProcessActionFormView,
    ChemicalDashboardActionView,
    ChemicalSpecificationFilterView,
    TestResultFilterView,
    RequestStatusTransitionView,
    ConfirmChemicalWorkflowActionView,
    ChemicalBatchUtilizationView,
    ReturnChemicalBatchView,
    CoAGenerationView,
    CoAApprovalView,
    PendingCoAApprovalView,
)

app_name = "ca"

workflow = FlowViewset(ChemicalAnalysisFlow)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path(
        "dashboard/action/",
        ChemicalDashboardActionView.as_view(),
        name="dashboard-action",
    ),

    path("batches/", ChemicalBatchListView.as_view(), name="batch-list"),
    path("batches/add/", ChemicalBatchCreateView.as_view(), name="batch-create"),
    path("batches/<int:pk>/", ChemicalBatchDetailView.as_view(), name="batch-detail"),
    path(
        "batches/<int:pk>/edit/",
        ChemicalBatchUpdateView.as_view(),
        name="batch-update",
    ),
    path(
        "batches/<int:pk>/transition/",
        TransitionBatchView.as_view(),
        name="batch-transition",
    ),
    path(
        "batches/<int:pk>/utilize/",
        ChemicalBatchUtilizationView.as_view(),
        name="batch-utilize",
    ),
    path(
        "batches/<int:pk>/return/",
        ReturnChemicalBatchView.as_view(),
        name="batch-return",
    ),
    path(
        "batches/<int:pk>/transition-direct/",
        TransitionBatchView.as_view(),
        name="batch-transition-direct",
    ),

    path("requests/", ChemicalAnalysisRequestListView.as_view(), name="request-list"),
    path(
        "requests/<int:pk>/",
        ChemicalAnalysisRequestDetailView.as_view(),
        name="request-detail",
    ),
    path(
        "requests/<int:pk>/transition/",
        RequestStatusTransitionView.as_view(),
        name="request-transition",
    ),

    path("processes/", ProcessListView.as_view(), name="process-list"),
    path(
        "processes/<int:pk>/",
        ProcessDetailView.as_view(),
        name="process-detail",
    ),
    path(
        "processes/<int:pk>/json/",
        ProcessJSONView.as_view(),
        name="process-json",
    ),
    path(
        "processes/<int:pk>/action/",
        ProcessActionView.as_view(),
        name="process-action",
    ),
    path(
        "processes/<int:pk>/action/form/",
        ChemicalProcessActionFormView.as_view(),
        name="process-action-form",
    ),
    path(
        "processes/<int:pk>/statistics/",
        ProcessStatisticsView.as_view(),
        name="process-statistics",
    ),
    path(
        "processes/<int:pk>/refresh/",
        ProcessRefreshView.as_view(),
        name="process-refresh",
    ),

    path(
        "analysis/inputs/<int:pk>/",
        ChemicalAnalysisInputDetailView.as_view(),
        name="analysis-input-detail",
    ),
    path(
        "analysis/inputs/<int:pk>/recalculate/",
        RecalculateAnalysisInputView.as_view(),
        name="analysis-input-recalculate",
    ),

    path(
        "specifications/",
        ChemicalSpecificationListView.as_view(),
        name="specification-list",
    ),
    path(
        "specifications/filter/",
        ChemicalSpecificationFilterView.as_view(),
        name="specification-filter",
    ),

    path("results/", ResultListView.as_view(), name="result-list"),
    path(
        "results/<int:pk>/",
        ResultDetailView.as_view(),
        name="result-detail",
    ),
    path(
        "results/filter/",
        TestResultFilterView.as_view(),
        name="result-filter",
    ),

    path("checklists/", ChecklistListView.as_view(), name="checklist-list"),
    path(
        "checklists/<int:pk>/",
        ChecklistDetailView.as_view(),
        name="checklist-detail",
    ),
    path(
        "checklists/<int:pk>/reopen/",
        ReopenChecklistView.as_view(),
        name="checklist-reopen",
    ),

    path("coa/", ChemicalCoAListView.as_view(), name="coa-list"),
    path(
        "coa/<int:pk>/",
        ChemicalCoADetailView.as_view(),
        name="coa-detail",
    ),
    path(
        "coa/<int:pk>/generate/",
        CoAGenerationView.as_view(),
        name="coa-generate",
    ),
    path(
        "coa/<int:pk>/regenerate/",
        RegenerateChemicalCoAView.as_view(),
        name="coa-regenerate",
    ),
    path(
        "coa/<int:pk>/approve/",
        CoAApprovalView.as_view(),
        name="coa-approve",
    ),
    path(
        "coa/<int:pk>/verify/",
        VerifyChemicalCoAView.as_view(),
        name="coa-verify",
    ),
    path(
        "coa/<int:pk>/download/",
        DownloadChemicalCoAView.as_view(),
        name="coa-download",
    ),

    path("tasks/", MyChemicalTasksView.as_view(), name="my-tasks"),
    path(
        "tasks/overdue/",
        OverdueAnalysisView.as_view(),
        name="overdue-analysis",
    ),
    path(
        "tasks/pending-analysis/",
        PendingAnalysisView.as_view(),
        name="pending-analysis",
    ),
    path(
        "tasks/pending-qa/",
        PendingQAReviewView.as_view(),
        name="pending-qa",
    ),
    path(
        "tasks/pending-approval/",
        PendingApprovalView.as_view(),
        name="pending-approval",
    ),
    path(
        "tasks/pending-coa/",
        PendingCoAApprovalView.as_view(),
        name="pending-coa-approval",
    ),

    path(
        "workflow/",
        workflow.urls,
    ),

    path(
        "workflow/confirm/<int:pk>/",
        ConfirmChemicalWorkflowActionView.as_view(),
        name="workflow-confirm",
    ),
]

