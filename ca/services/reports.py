# ca/services/reports.py

from ca.services.analytics import (
    ChemicalAnalyticsService
)


class ReportService:

    @staticmethod
    def executive_summary():
        return {
            "summary":
                ChemicalAnalyticsService.summary(),
            "yield":
                ChemicalAnalyticsService.yield_statistics(),
            "status":
                list(
                    ChemicalAnalyticsService
                    .batches_by_status()
                ),
        }