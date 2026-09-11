# ca/services/analytics.py

from django.db.models import (
    Avg,
    Count,
    Sum,
    Min,
    Max,
)
from django.db.models.functions import TruncMonth

from ca.models import (
    ChemicalBatch,
    BatchTestResult,
)


class ChemicalAnalyticsService:

    @staticmethod
    def summary():
        return {
            "batches": ChemicalBatch.objects.count(),
            "tests": BatchTestResult.objects.count(),
            "avg_yield":
                ChemicalBatch.objects.aggregate(
                    value=Avg("yield_percent")
                )["value"] or 0,
        }

    @staticmethod
    def monthly_batches():
        return (
            ChemicalBatch.objects
            .annotate(
                month=TruncMonth(
                    "created_at"
                )
            )
            .values("month")
            .annotate(
                total=Count("id")
            )
            .order_by("month")
        )

    @staticmethod
    def yield_statistics():
        return ChemicalBatch.objects.aggregate(
            avg=Avg("yield_percent"),
            min=Min("yield_percent"),
            max=Max("yield_percent"),
        )

    @staticmethod
    def batches_by_status():
        return (
            ChemicalBatch.objects
            .values("status")
            .annotate(
                total=Count("id")
            )
        )

    @staticmethod
    def chemical_consumption():
        return (
            ChemicalBatch.objects
            .values("chemical__name")
            .annotate(
                total=Sum("quantity")
            )
            .order_by("-total")
        )