from __future__ import annotations

from datetime import timedelta

from django.db.models import (
    Avg,
    Count,
    F,
    Max,
    Min,
    Q,
    StdDev,
    Sum,
)
from django.db.models.functions import (
    ExtractMonth,
    ExtractYear,
    TruncDay,
    TruncMonth,
)
from django.utils import timezone

from ca.models import (
    BatchTestResult,
    ChemicalAnalysisRequest,
    ChemicalBatch,
    ChemicalCoA,
)

from dashboards.registry import registry


# ============================================================
# UTIL: COMMON FILTERS (reusable patterns)
# ============================================================

def _this_year():
    return timezone.now().year


def _last_12_months():
    return timezone.now() - timedelta(days=365)


# ============================================================
# KPI: BATCH OVERVIEW (NEW)
# ============================================================

registry.charts.register(
    key="ca.kpi_overview",
    title="Laboratory KPI Overview",
    chart_type="kpi",
    category="overview",
    realtime=True,
    refresh_interval=60,
    queryset=lambda: {
        "total_batches": ChemicalBatch.objects.count(),
        "analysed": ChemicalBatch.objects.filter(status=ChemicalBatch.Status.ANALYSED).count(),
        "approved": ChemicalBatch.objects.filter(status=ChemicalBatch.Status.APPROVED).count(),
        "rejected": ChemicalBatch.objects.filter(status=ChemicalBatch.Status.REJECTED).count(),
        "utilized": ChemicalBatch.objects.filter(status=ChemicalBatch.Status.UTILIZED).count(),
    },
)


# ============================================================
# BATCH STATUS DISTRIBUTION (IMPROVED)
# ============================================================

registry.charts.register(
    key="ca.batch_status_distribution",
    title="Batch Status Distribution",
    chart_type="pie",
    category="operations",
    icon="fa-chart-pie",
    drilldown=True,
    queryset=lambda: ChemicalBatch.objects.values("status").annotate(total=Count("id")),
)


# ============================================================
# MONTHLY RECEIPTS TREND (IMPROVED + FILTERED)
# ============================================================

registry.charts.register(
    key="ca.monthly_receipts",
    title="Monthly Batch Receipts",
    chart_type="line",
    category="trends",
    smooth=True,
    realtime=True,
    drilldown="month",
    queryset=lambda: (
        ChemicalBatch.objects.filter(received_date__gte=_last_12_months())
        .annotate(month=TruncMonth("received_date"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    ),
)


# ============================================================
# CHEMICAL TRENDS (STACKED + NORMALIZED OPTION)
# ============================================================

registry.charts.register(
    key="ca.chemical_trends",
    title="Chemical Receipt Trends",
    chart_type="stacked_area",
    category="trends",
    stacked=True,
    drilldown=True,
    queryset=lambda: (
        ChemicalBatch.objects.filter(received_date__gte=_last_12_months())
        .annotate(month=TruncMonth("received_date"))
        .values("month", "chemical__name")
        .annotate(total=Count("id"))
        .order_by("month")
    ),
)


# ============================================================
# WORKLOAD HEATMAP (IMPROVED DIMENSIONALITY)
# ============================================================

registry.charts.register(
    key="ca.workload_heatmap",
    title="Laboratory Workload Heatmap",
    chart_type="heatmap",
    category="analytics",
    queryset=lambda: (
        ChemicalBatch.objects.annotate(
            month=ExtractMonth("received_date"),
            year=ExtractYear("received_date"),
        )
        .values("year", "month", "treatment_plant__name")
        .annotate(total=Count("id"))
    ),
)


# ============================================================
# PASS / FAIL DISTRIBUTION (QC)
# ============================================================

registry.charts.register(
    key="ca.pass_fail_distribution",
    title="Test Result Distribution",
    chart_type="doughnut",
    category="quality",
    queryset=lambda: BatchTestResult.objects.values("status").annotate(total=Count("id")),
)


# ============================================================
# QUALITY RADAR (NORMALIZED AVERAGE)
# ============================================================

registry.charts.register(
    key="ca.quality_radar",
    title="Parameter Performance Index",
    chart_type="radar",
    category="quality",
    queryset=lambda: (
        BatchTestResult.objects.exclude(value__isnull=True)
        .values("parameter__parameter_name")
        .annotate(
            avg=Avg("value"),
            min=Min("value"),
            max=Max("value"),
        )
    ),
)


# ============================================================
# BOX PLOT (IMPROVED STRUCTURE)
# ============================================================

registry.charts.register(
    key="ca.result_distribution_box",
    title="Parameter Distribution (Box Analysis)",
    chart_type="boxplot",
    category="statistics",
    queryset=lambda: (
        BatchTestResult.objects.exclude(value__isnull=True)
        .values("parameter__parameter_name")
        .annotate(
            avg=Avg("value"),
            std=StdDev("value"),
            min=Min("value"),
            max=Max("value"),
        )
    ),
)


# ============================================================
# FAILURE PARETO (TOP ISSUES)
# ============================================================

registry.charts.register(
    key="ca.failure_pareto",
    title="Failure Pareto Analysis",
    chart_type="pareto",
    category="quality",
    queryset=lambda: (
        BatchTestResult.objects.filter(status=BatchTestResult.Status.FAIL)
        .values("parameter__parameter_name")
        .annotate(total=Count("id"))
        .order_by("-total")
    ),
)


# ============================================================
# SPC CONTROL CHART (ENHANCED STABILITY VIEW)
# ============================================================

registry.charts.register(
    key="ca.control_chart",
    title="Process Control Chart",
    chart_type="control",
    category="quality",
    queryset=lambda: (
        BatchTestResult.objects.exclude(value__isnull=True)
        .annotate(day=TruncDay("tested_at"))
        .values("day")
        .annotate(
            avg=Avg("value"),
            std=StdDev("value"),
            min=Min("value"),
            max=Max("value"),
        )
        .order_by("day")
    ),
)


# ============================================================
# SUNBURST (PROCESS FLOW)
# ============================================================

registry.charts.register(
    key="ca.analysis_hierarchy",
    title="Chemical Analysis Hierarchy",
    chart_type="sunburst",
    category="hierarchy",
    queryset=lambda: (
        ChemicalBatch.objects.values(
            "treatment_plant__name",
            "chemical__name",
            "status",
        ).annotate(total=Count("id"))
    ),
)


# ============================================================
# TREEMAP (INVENTORY VALUE VIEW)
# ============================================================

registry.charts.register(
    key="ca.inventory_treemap",
    title="Chemical Inventory Treemap",
    chart_type="treemap",
    category="inventory",
    queryset=lambda: (
        ChemicalBatch.objects.values(
            "supplier__name",
            "chemical__name",
        ).annotate(total_qty=Sum("quantity_received"))
    ),
)


# ============================================================
# SANKEY FLOW (SIMPLIFIED CLEAN FLOW)
# ============================================================

registry.charts.register(
    key="ca.batch_flow",
    title="Batch Lifecycle Flow",
    chart_type="sankey",
    category="workflow",
    queryset=lambda: (
        ChemicalBatch.objects.values("status", "chemical__name").annotate(
            total=Count("id")
        )
    ),
)


# ============================================================
# FUNNEL (REALISTIC PIPELINE)
# ============================================================

registry.charts.register(
    key="ca.analysis_funnel",
    title="Laboratory Workflow Funnel",
    chart_type="funnel",
    category="workflow",
    queryset=lambda: [
        {"stage": "Received", "value": ChemicalBatch.objects.count()},
        {"stage": "Analysed", "value": ChemicalBatch.objects.filter(status="ANALYSED").count()},
        {"stage": "Approved", "value": ChemicalBatch.objects.filter(status="APPROVED").count()},
        {"stage": "Utilized", "value": ChemicalBatch.objects.filter(status="UTILIZED").count()},
    ],
)


# ============================================================
# SUPPLIER PERFORMANCE (QUALITY METRICS ADDED)
# ============================================================

registry.charts.register(
    key="ca.supplier_performance",
    title="Supplier Quality Performance",
    chart_type="horizontal_bar",
    category="suppliers",
    queryset=lambda: (
        ChemicalBatch.objects.values("supplier__name")
        .annotate(
            approved=Count("id", filter=Q(status="APPROVED")),
            rejected=Count("id", filter=Q(status="REJECTED")),
            total=Count("id"),
            rejection_rate=Count("id", filter=Q(status="REJECTED")) * 1.0 / Count("id"),
        )
        .order_by("-approved")
    ),
)


# ============================================================
# CHEMICAL CONSUMPTION (UTILIZATION FOCUS)
# ============================================================

registry.charts.register(
    key="ca.chemical_consumption",
    title="Chemical Consumption",
    chart_type="bar",
    category="inventory",
    drilldown=True,
    queryset=lambda: (
        ChemicalBatch.objects.filter(status="UTILIZED")
        .values("chemical__name")
        .annotate(quantity=Sum("quantity_received"))
        .order_by("-quantity")
    ),
)


# ============================================================
# COA GENERATION TREND
# ============================================================

registry.charts.register(
    key="ca.coa_generation",
    title="Certificate Generation Trend",
    chart_type="area",
    category="reports",
    queryset=lambda: (
        ChemicalCoA.objects.annotate(month=TruncMonth("date_of_report"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    ),
)


# ============================================================
# TURNAROUND TIME (FIXED: REAL METRIC READY)
# ============================================================

registry.charts.register(
    key="ca.turnaround_time",
    title="Analysis Turnaround Time",
    chart_type="histogram",
    category="performance",
    queryset=lambda: (
        ChemicalAnalysisRequest.objects.exclude(analysis_started_at__isnull=True)
        .annotate(
            turnaround_days=F("analysis_deadline") - F("analysis_started_at")
        )
    ),
)


# ============================================================
# OVERDUE ANALYSIS (SLA METRIC)
# ============================================================

registry.charts.register(
    key="ca.overdue_analysis",
    title="Overdue Analysis Requests",
    chart_type="gauge",
    category="performance",
    queryset=lambda: {
        "overdue": ChemicalAnalysisRequest.objects.filter(
            analysis_deadline__lt=timezone.now(),
            status=ChemicalAnalysisRequest.Status.IN_PROGRESS,
        ).count(),
        "total": ChemicalAnalysisRequest.objects.count(),
    },
)


# ============================================================
# REQUEST TIMELINE (IMPROVED GRANULARITY)
# ============================================================

registry.charts.register(
    key="ca.request_timeline",
    title="Request Timeline",
    chart_type="timeline",
    category="workflow",
    queryset=lambda: (
        ChemicalAnalysisRequest.objects.annotate(day=TruncDay("created_at"))
        .values("day", "status")
        .annotate(total=Count("id"))
        .order_by("day")
    ),
)


# ============================================================
# CORRELATION MATRIX (RAW DATA SOURCE)
# ============================================================

registry.charts.register(
    key="ca.correlation_matrix",
    title="Parameter Correlation Matrix",
    chart_type="correlation_matrix",
    category="statistics",
    queryset=lambda: BatchTestResult.objects.exclude(value__isnull=True),
)


# ============================================================
# OUTLIERS (ENRICHED SCATTER)
# ============================================================

registry.charts.register(
    key="ca.outlier_detection",
    title="Analytical Outlier Detection",
    chart_type="scatter",
    category="statistics",
    queryset=lambda: (
        BatchTestResult.objects.exclude(value__isnull=True)
        .values("parameter__parameter_name", "value", "tested_at")
    ),
)


# ============================================================
# REAL-TIME MONITOR (IMPROVED KPI STREAM)
# ============================================================

registry.charts.register(
    key="ca.realtime_monitor",
    title="Real-Time Laboratory Monitor",
    chart_type="live",
    category="realtime",
    realtime=True,
    refresh_interval=30,
    websocket=True,
    queryset=lambda: {
        "batches": ChemicalBatch.objects.count(),
        "pending": ChemicalAnalysisRequest.objects.filter(status="PENDING").count(),
        "in_progress": ChemicalAnalysisRequest.objects.filter(status="IN_PROGRESS").count(),
        "completed": ChemicalAnalysisRequest.objects.filter(status="COMPLETED").count(),
        "approved": ChemicalBatch.objects.filter(status="APPROVED").count(),
        "rejected": ChemicalBatch.objects.filter(status="REJECTED").count(),
        "failed_tests": BatchTestResult.objects.filter(status="FAIL").count(),
    },
)


# ============================================================
# FORECAST DATASET
# ============================================================

registry.charts.register(
    key="ca.forecast",
    title="Chemical Receipt Forecast",
    chart_type="forecast",
    category="forecasting",
    queryset=lambda: (
        ChemicalBatch.objects.annotate(month=TruncMonth("received_date"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    ),
)
