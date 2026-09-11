from dashboards.registry import registry
from ca.models import (
    ChemicalBatch,
    ChemicalCoA,
)


registry.reports.register(
    key="ca.batch_register",
    label="Chemical Batch Register",
    queryset=lambda:
        ChemicalBatch.objects.select_related(
            "chemical",
            "supplier",
            "treatment_plant",
        ),
)


registry.reports.register(
    key="ca.coa_register",
    label="Certificate Register",
    queryset=lambda:
        ChemicalCoA.objects.select_related(
            "batch",
        ),
)