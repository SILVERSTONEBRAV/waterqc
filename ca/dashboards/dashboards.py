from dashboards import dashboards
from dashboards.definitions import DashboardDefinition

dashboards.register(
    "ca",
    DashboardDefinition(
        key="ca",
        name="Chemical Analysis Intelligence Center",
        slug="chemical-analysis",

        icon="fa-solid fa-flask-vial",
        color="#0284c7",
        accent="cyan",

        group="Laboratory",
        order=10,

        category="Quality Assurance",
        priority="high",

        description="""
        Enterprise dashboard for chemical quality management,
        laboratory analytics, certificates of analysis,
        supplier intelligence and predictive analytics.
        """,

        permissions=(
            "ca.view_chemicalbatch",
            "ca.view_chemicalanalysisrequest",
            "ca.view_batchtestresult",
            "ca.view_chemicalcoa",
        ),

        tags=(
            "laboratory",
            "quality",
            "chemicals",
            "analytics",
            "compliance",
        ),

        realtime=True,
        mobile_enabled=True,

        url_name="ca:dashboard",
        url="/dashboards/chemical-analysis/",

        websocket_group="ca_dashboard_updates",
        websocket_endpoint="/ws/dashboard/ca/",
        refresh_interval=30,

        cache_timeout=300,
        cache_key="dashboard_ca",

        widgets=(
            "ca_summary_cards",
            "recent_batches",
            "supplier_ranking",
            "overdue_requests",
            "coa_status",
        ),

        charts=(
            "batch_status_distribution",
            "approval_trend",
            "supplier_performance",
            "failure_heatmap",
            "chemical_trend",
        ),

        kpis=(
            "batches_received",
            "batches_approved",
            "batches_rejected",
            "pending_requests",
            "overdue_requests",
            "analysis_turnaround",
        ),

        reports=(
            "chemical_batch_report",
            "coa_report",
            "supplier_report",
            "compliance_report",
        ),

        forecasts=(
            "chemical_demand_forecast",
        ),

        analytics=(
            "supplier_intelligence",
            "failure_analysis",
            "plant_performance",
        ),

        ml_models=(
            "batch_failure_prediction",
            "supplier_risk_prediction",
        ),

        notifications=(
            "batch_rejected",
            "analysis_overdue",
            "coa_generated",
        ),

        searchable_models=(
            "ChemicalBatch",
            "ChemicalAnalysisRequest",
            "BatchTestResult",
            "ChemicalCoA",
            "Chemical",
            "Supplier",
        ),

        export_formats=(
            "pdf",
            "xlsx",
            "csv",
            "json",
            "doc"
        ),

        owner="Quality Assurance Department",
        version="2.0.0",
        tenant_aware=True,
        audit_enabled=True,
    ),
)