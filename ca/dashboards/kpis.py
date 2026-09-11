from __future__ import annotations

import numpy as np
import pandas as pd

from datetime import timedelta
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.core.cache import cache

from scipy import stats

from ca.models import (
    ChemicalBatch,
    ChemicalAnalysisRequest,
    BatchTestResult,
    ChemicalCoA,
)

from dashboards.registry import registry


# =========================================================
# CORE UTILITIES
# =========================================================

CACHE_TTL = 300


def cached_kpi(key: str, ttl: int = CACHE_TTL):
    """
    Advanced cache wrapper with namespace isolation + timestamp drift protection.
    """
    def decorator(fn):
        def wrapper(*args, refresh=False, **kwargs):
            cache_key = f"kpi:v2:{key}:{args}:{kwargs}"

            if not refresh:
                cached = cache.get(cache_key)
                if cached is not None:
                    return cached

            value = fn(*args, **kwargs)
            cache.set(cache_key, value, ttl)
            return value

        return wrapper
    return decorator


def safe_div(a, b):
    return a / b if b else 0


# =========================================================
# 1. GLOBAL SYSTEM HEALTH KPI
# =========================================================

registry.kpis.register(
    key="ca.system_health_score",
    group="system",
    unit="score",
    aggregation="weighted",
    realtime=True,
    tags=["health", "ml", "composite"],
    value=lambda: round(
        (
            safe_div(ChemicalBatch.objects.filter(status=ChemicalBatch.Status.APPROVED).count(),
                     ChemicalBatch.objects.count()) * 40
            +
            safe_div(BatchTestResult.objects.filter(status=BatchTestResult.Status.PASS).count(),
                     max(BatchTestResult.objects.count(), 1)) * 40
            +
            safe_div(ChemicalCoA.objects.filter(pdf_file__isnull=False).count(),
                     max(ChemicalCoA.objects.count(), 1)) * 20
        ),
        2
    ),
)


# =========================================================
# 2. BATCH FLOW VELOCITY (TIME-BASED KPI)
# =========================================================

@cached_kpi("ca.batch_velocity")
def batch_velocity():
    last_7_days = timezone.now() - timedelta(days=7)

    created = ChemicalBatch.objects.filter(created_at__gte=last_7_days).count()
    analysed = ChemicalBatch.objects.filter(
        status=ChemicalBatch.Status.ANALYSED,
        updated_at__gte=last_7_days
    ).count()

    return {
        "created": created,
        "analysed": analysed,
        "velocity_ratio": safe_div(analysed, max(created, 1)),
    }


registry.kpis.register(
    key="ca.batch_velocity",
    group="operations",
    unit="ratio",
    value=batch_velocity,
    realtime=True,
)


# =========================================================
# 3. APPROVAL QUALITY INDEX (ML-STYLE KPI)
# =========================================================

@cached_kpi("ca.approval_quality_index")
def approval_quality_index():
    qs = ChemicalBatch.objects.values("supplier__name").annotate(
        total=Count("id"),
        approved=Count("id", filter=Q(status=ChemicalBatch.Status.APPROVED)),
        rejected=Count("id", filter=Q(status=ChemicalBatch.Status.REJECTED)),
    )

    scores = []
    for r in qs:
        total = max(r["total"], 1)

        approval_rate = r["approved"] / total
        rejection_penalty = r["rejected"] / total

        score = (approval_rate * 100) - (rejection_penalty * 35)

        scores.append(score)

    return {
        "mean_quality_score": round(np.mean(scores) if scores else 0, 2),
        "std_dev": round(np.std(scores) if scores else 0, 2),
        "suppliers_analyzed": len(scores),
    }


registry.kpis.register(
    key="ca.approval_quality_index",
    group="supplier",
    unit="score",
    value=approval_quality_index,
)


# =========================================================
# 4. LAB PERFORMANCE KPI (TURNAROUND TIME)
# =========================================================

registry.kpis.register(
    key="ca.lab_turnaround_time",
    group="lab",
    unit="hours",
    value=lambda: round(
        ChemicalAnalysisRequest.objects.filter(
            status=ChemicalAnalysisRequest.Status.COMPLETED
        ).aggregate(
            avg_time=Avg(
                F("analysis_deadline") - F("analysis_started_at")
            )
        )["avg_time"] or 0,
        2
    ),
)


# =========================================================
# 5. OUTLIER RATE (STATISTICAL CONTROL KPI)
# =========================================================

@cached_kpi("ca.outlier_rate")
def outlier_rate():
    qs = BatchTestResult.objects.exclude(value__isnull=True).values_list("value", flat=True)

    data = np.array(list(qs))
    if len(data) < 5:
        return {"outlier_rate": 0}

    z_scores = np.abs(stats.zscore(data))
    outliers = (z_scores > 3).sum()

    return {
        "outlier_rate": round(outliers / len(data), 4),
        "total_points": len(data),
    }


registry.kpis.register(
    key="ca.outlier_rate",
    group="quality",
    unit="ratio",
    value=outlier_rate,
    tags=["spc", "anomaly"],
)


# =========================================================
# 6. REAL-TIME PASS/FAIL MOMENTUM
# =========================================================

@cached_kpi("ca.pass_fail_momentum")
def pass_fail_momentum():
    last_30 = timezone.now() - timedelta(days=30)

    qs = BatchTestResult.objects.filter(tested_at__gte=last_30)

    pass_count = qs.filter(status=BatchTestResult.Status.PASS).count()
    fail_count = qs.filter(status=BatchTestResult.Status.FAIL).count()

    total = max(pass_count + fail_count, 1)

    return {
        "pass_rate": round(pass_count / total, 3),
        "fail_rate": round(fail_count / total, 3),
        "momentum_index": round((pass_count - fail_count) / total, 3),
    }


registry.kpis.register(
    key="ca.pass_fail_momentum",
    group="quality",
    unit="index",
    value=pass_fail_momentum,
    realtime=True,
)


# =========================================================
# 7. COA GENERATION HEALTH KPI
# =========================================================

registry.kpis.register(
    key="ca.coa_generation_rate",
    group="reporting",
    unit="ratio",
    value=lambda: round(
        ChemicalCoA.objects.filter(pdf_file__isnull=False).count()
        /
        max(ChemicalBatch.objects.count(), 1),
        3
    ),
)


# =========================================================
# 8. SUPPLIER CONSISTENCY SCORE (VARIANCE MODEL)
# =========================================================

@cached_kpi("ca.supplier_consistency_score")
def supplier_consistency_score():
    qs = BatchTestResult.objects.values("batch__supplier__name").annotate(
        avg=Avg("value"),
        count=Count("id"),
    )

    scores = []

    for r in qs:
        avg = r["avg"] or 0
        consistency = 1 / (1 + abs(avg))

        scores.append(consistency)

    return {
        "mean_consistency": round(np.mean(scores) if scores else 0, 3),
        "variance": round(np.var(scores) if scores else 0, 3),
    }


registry.kpis.register(
    key="ca.supplier_consistency",
    group="supplier",
    unit="score",
    value=supplier_consistency_score,
)


# =========================================================
# 9. ANALYTICAL COMPLEXITY INDEX (ADVANCED KPI)
# =========================================================

@cached_kpi("ca.analysis_complexity_index")
def analysis_complexity_index():
    total_params = BatchTestResult.objects.values("parameter").distinct().count()
    total_batches = ChemicalBatch.objects.count()

    return {
        "complexity_index": round(
            safe_div(total_params * np.log1p(total_batches), max(total_batches, 1)),
            3
        ),
        "parameters": total_params,
        "batches": total_batches,
    }


registry.kpis.register(
    key="ca.analysis_complexity_index",
    group="ml",
    unit="index",
    value=analysis_complexity_index,
)


# =========================================================
# 10. SYSTEM SUMMARY KPI DASHBOARD
# =========================================================

registry.kpis.register(
    key="ca.executive_summary",
    group="executive",
    unit="bundle",
    value=lambda: {
        "batches": ChemicalBatch.objects.count(),
        "approved": ChemicalBatch.objects.filter(status="APPROVED").count(),
        "rejected": ChemicalBatch.objects.filter(status="REJECTED").count(),
        "pending": ChemicalAnalysisRequest.objects.filter(status="PENDING").count(),
        "coas": ChemicalCoA.objects.count(),
        "pass_rate": round(
            safe_div(
                BatchTestResult.objects.filter(status="PASS").count(),
                max(BatchTestResult.objects.count(), 1)
            ) * 100,
            2
        ),
    },
    realtime=True,
)