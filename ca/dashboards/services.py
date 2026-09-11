# ca/dashboards/services.py

from dashboards.registry import registry

from ca.services.analytics import (
    ChemicalAnalyticsService
)
from ca.services.forecasting import (
    ForecastingService
)
from ca.services.reports import (
    ReportService
)
from ca.services.ml import (
    MLService
)


registry.analytics.register(
    key="ca.summary",
    obj=ChemicalAnalyticsService.summary,
)

registry.analytics.register(
    key="ca.monthly_batches",
    obj=ChemicalAnalyticsService.monthly_batches,
)

registry.analytics.register(
    key="ca.yield_stats",
    obj=ChemicalAnalyticsService.yield_statistics,
)

registry.forecasts.register(
    key="ca.batch_forecast",
    obj=ForecastingService.batch_forecast,
)

registry.reports.register(
    key="ca.executive_report",
    obj=ReportService.executive_summary,
)

registry.ml_models.register(
    key="ca.anomaly_detection",
    obj=MLService.anomaly_detection,
)