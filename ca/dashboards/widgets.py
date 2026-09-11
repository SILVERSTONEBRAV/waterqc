from ca.models import (
    ChemicalBatch,
    ChemicalAnalysisRequest,
)

from dashboards.registry import registry


registry.widgets.register(
    key="ca.recent_batches",
    title="Recent Batches",
    component="table",
    queryset=lambda:
        ChemicalBatch.objects.select_related(
            "chemical",
            "supplier",
            "treatment_plant",
        ).order_by(
            "-created_at"
        )[:20],
)


registry.widgets.register(
    key="ca.pending_analysis",
    title="Pending Analysis Requests",
    component="table",
    queryset=lambda:
        ChemicalAnalysisRequest.objects.filter(
            status=ChemicalAnalysisRequest.Status.PENDING
        ),
)