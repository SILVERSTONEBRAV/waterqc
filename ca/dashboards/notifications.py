from django.utils import timezone
from datetime import timedelta

from dashboards.registry import registry
from ca.models import (
    ChemicalAnalysisRequest,
)


@registry.notifications.register(
    key="ca.overdue_analysis"
)
def overdue_analysis():

    return list(
        ChemicalAnalysisRequest.objects.filter(
            analysis_deadline__lt=timezone.now(),
            status="IN_PROGRESS",
        )
    )