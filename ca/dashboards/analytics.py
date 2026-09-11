from __future__ import annotations

import numpy as np
import pandas as pd

from django.db.models import Avg, Count, Q, StdDev, Min, Max
from django.core.cache import cache

from scipy import stats
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

try:
    from prophet import Prophet
    HAS_PROPHET = True
except Exception:
    HAS_PROPHET = False


from ca.models import ChemicalBatch, BatchTestResult

from dashboards.registry import analytics


# =========================================================
# SHARED UTILITIES (SAFE CACHE LAYER)
# =========================================================

CACHE_TTL = 300


def cached(key: str):
    """
    Lightweight deterministic cache wrapper.
    Works independently of registry cache system.
    """
    def decorator(fn):
        def wrapper(*args, **kwargs):
            cache_key = f"analytics:ca:{key}"

            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            result = fn(*args, **kwargs)
            cache.set(cache_key, result, CACHE_TTL)
            return result

        return wrapper
    return decorator


# =========================================================
# 1. SUPPLIER QUALITY SCORE (ROBUST + NORMALIZED)
# =========================================================

@analytics.register(
    key="ca.supplier_quality_score",
    tags=["supplier", "quality"],
    feature=True,
)
@cached("supplier_quality_score")
def supplier_quality_score():

    qs = (
        ChemicalBatch.objects
        .values("supplier__name")
        .annotate(
            total=Count("id"),
            approved=Count("id", filter=Q(status="APPROVED")),
            rejected=Count("id", filter=Q(status="REJECTED")),
        )
    )

    results = []

    for row in qs:
        total = max(row["total"], 1)

        approval_rate = row["approved"] / total
        rejection_rate = row["rejected"] / total

        # normalized scoring (bounded stability)
        score = (approval_rate * 100) - (rejection_rate * 35)
        score = np.clip(score, 0, 100)

        results.append({
            "supplier": row["supplier__name"],
            "quality_score": round(float(score), 2),
            "approval_rate": round(float(approval_rate), 4),
            "rejection_rate": round(float(rejection_rate), 4),
        })

    return sorted(results, key=lambda x: x["quality_score"], reverse=True)


# =========================================================
# 2. PARAMETER STATISTICS (SPC-READY)
# =========================================================

@analytics.register(
    key="ca.parameter_statistics",
    tags=["lab", "statistics", "quality"]
)
def parameter_statistics():

    qs = (
        BatchTestResult.objects
        .exclude(value__isnull=True)
        .values("parameter__parameter_name")
        .annotate(
            mean=Avg("value"),
            std=StdDev("value"),
            min=Min("value"),
            max=Max("value"),
            count=Count("id"),
        )
    )

    out = []

    for r in qs:
        std = r["std"] or 0.0
        rng = (r["max"] or 0) - (r["min"] or 0)

        cp = rng / (6 * std) if std > 0 else 0.0

        out.append({
            "parameter": r["parameter__parameter_name"],
            "mean": round(r["mean"] or 0, 4),
            "std": round(std, 4),
            "min": r["min"],
            "max": r["max"],
            "cp_index": round(cp, 4),
            "samples": r["count"],
        })

    return out


# =========================================================
# 3. ANOMALY DETECTION (ROBUST ISOLATION FOREST)
# =========================================================

@analytics.register(
    key="ca.anomaly_detection",
    tags=["ml", "outliers"]
)
def anomaly_detection():

    qs = (
        BatchTestResult.objects
        .exclude(value__isnull=True)
        .values("value", "parameter__parameter_name")
    )

    df = pd.DataFrame(list(qs))
    if df.empty:
        return []

    scaler = StandardScaler()
    df["value_scaled"] = scaler.fit_transform(df[["value"]])

    model = IsolationForest(
        contamination=0.05,
        random_state=42,
        n_estimators=150,
    )

    df["anomaly"] = model.fit_predict(df[["value_scaled"]])

    return df[df["anomaly"] == -1].to_dict("records")


# =========================================================
# 4. TIME SERIES FORECAST (PROP HET + FALLBACK)
# =========================================================

@analytics.register(
    key="ca.batch_forecast",
    tags=["forecast", "time-series"]
)
def batch_forecast():

    qs = (
        ChemicalBatch.objects
        .values("received_date")
        .annotate(y=Count("id"))
        .order_by("received_date")
    )

    df = pd.DataFrame(list(qs))
    if df.empty:
        return []

    df = df.rename(columns={"received_date": "ds"})

    if HAS_PROPHET:
        model = Prophet(daily_seasonality=True)
        model.fit(df)

        future = model.make_future_dataframe(periods=30)
        forecast = model.predict(future)

        return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(30).to_dict("records")

    # fallback: rolling mean projection
    df["rolling"] = df["y"].rolling(7, min_periods=1).mean()

    return df.tail(30).to_dict("records")


# =========================================================
# 5. PARAMETER CORRELATION MATRIX
# =========================================================

@analytics.register(
    key="ca.parameter_correlation",
    tags=["ml", "correlation"]
)
def parameter_correlation():

    qs = (
        BatchTestResult.objects
        .exclude(value__isnull=True)
        .values("batch_id", "parameter__parameter_name", "value")
    )

    df = pd.DataFrame(list(qs))
    if df.empty:
        return {}

    pivot = df.pivot_table(
        index="batch_id",
        columns="parameter__parameter_name",
        values="value"
    ).fillna(0)

    corr = pivot.corr().fillna(0)

    return corr.to_dict()


# =========================================================
# 6. SUPPLIER CONSISTENCY SCORE (VARIANCE MODEL)
# =========================================================

@analytics.register(
    key="ca.supplier_consistency",
    tags=["supplier", "quality"]
)
def supplier_consistency():

    qs = (
        BatchTestResult.objects
        .values("batch__supplier__name")
        .annotate(
            std=StdDev("value"),
            avg=Avg("value"),
            count=Count("id"),
        )
    )

    results = []

    for r in qs:
        std = r["std"] or 1.0

        consistency = 1 / (1 + std)

        results.append({
            "supplier": r["batch__supplier__name"],
            "consistency_score": round(consistency, 4),
            "std_dev": round(std, 4),
            "avg": r["avg"],
        })

    return sorted(results, key=lambda x: x["consistency_score"], reverse=True)


# =========================================================
# 7. SPC Z-SCORE OUTLIERS
# =========================================================

@analytics.register(
    key="ca.process_control_zscore",
    tags=["spc", "quality"]
)
def process_control_zscore():

    qs = (
        BatchTestResult.objects
        .exclude(value__isnull=True)
        .values("parameter__parameter_name", "value")
    )

    df = pd.DataFrame(list(qs))
    if df.empty:
        return []

    df["zscore"] = df.groupby("parameter__parameter_name")["value"].transform(
        lambda x: np.abs(stats.zscore(x, nan_policy="omit"))
    )

    return df[df["zscore"] > 3].to_dict("records")


# =========================================================
# 8. PCA QUALITY REDUCTION MODEL
# =========================================================

@analytics.register(
    key="ca.parameter_pca",
    tags=["ml", "dimensionality"]
)
def parameter_pca():

    qs = (
        BatchTestResult.objects
        .exclude(value__isnull=True)
        .values("batch_id", "parameter__parameter_name", "value")
    )

    df = pd.DataFrame(list(qs))
    if df.empty:
        return []

    pivot = df.pivot_table(
        index="batch_id",
        columns="parameter__parameter_name",
        values="value"
    ).fillna(0)

    scaled = StandardScaler().fit_transform(pivot)

    pca = PCA(n_components=2)
    components = pca.fit_transform(scaled)

    return [
        {
            "batch": batch,
            "pc1": float(c[0]),
            "pc2": float(c[1]),
        }
        for batch, c in zip(pivot.index, components)
    ]


# =========================================================
# 9. REAL-TIME QUALITY INDEX
# =========================================================

@analytics.register(
    key="ca.real_time_quality_index",
    tags=["realtime", "quality"]
)
def real_time_quality_index():

    qs = BatchTestResult.objects.values("status")

    total = qs.count()
    if total == 0:
        return {"quality_index": 0}

    pass_count = qs.filter(status="PASS").count()
    fail_count = qs.filter(status="FAIL").count()

    return {
        "quality_index": round((pass_count - fail_count) / total, 4),
        "pass_rate": round(pass_count / total, 4),
        "fail_rate": round(fail_count / total, 4),
        "total": total,
    }