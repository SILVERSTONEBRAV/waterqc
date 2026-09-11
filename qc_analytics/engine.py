import io
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import skew, kurtosis, zscore, linregress
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.cluster import DBSCAN
from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA

from django.core.cache import cache
from django.utils.timezone import now
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from celery import shared_task
from django.apps import apps

# Domain Models
from qc.models import NonConformity, Cause, NonConformityStatus, WaterAnalysis

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent

class QuantumQCAnalyticsEngineV4:
    """Hybrid predictive/statistical engine for QC analytics (AI-Free v4.0)."""

    CHANNEL_LAYER = get_channel_layer()

    # -------------------------
    # 1️⃣ Aggregate all QC results dynamically
    # -------------------------
    @classmethod
    def aggregate_results(cls, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
        frames = []
        qc_app_models = apps.get_app_config("qc").get_models()
        for model in qc_app_models:
            if hasattr(model, "analysis") and hasattr(model, "value"):
                qs = model.objects.select_related(
                    "parameter", "analysis", "analysis__treatment_plant", "analysis__treatment_plant_phase"
                )
                if start and end:
                    qs = qs.filter(analysis__created_at__range=[start, end])

                rows = [
                    {
                        "plant": r.analysis.treatment_plant.name,
                        "phase": r.analysis.treatment_plant_phase.name,
                        "parameter": str(r.parameter),
                        "value": float(r.value),
                        "timestamp": r.analysis.created_at,
                        "analysis_id": r.analysis.id
                    }
                    for r in qs
                ]
                if rows:
                    frames.append(pd.DataFrame(rows))

        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames).sort_values("timestamp")
        return df

    # -------------------------
    # 2️⃣ Hybrid Anomaly Detection
    # -------------------------
    @staticmethod
    def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        df["anomaly"] = False
        df["zscore"] = zscore(df["value"])
        try:
            for param in df["parameter"].unique():
                subset = df[df["parameter"] == param]
                if len(subset) < 10:
                    continue
                X = StandardScaler().fit_transform(subset[["value"]])
                iso = IsolationForest(n_estimators=300, contamination=0.05, random_state=42)
                dbs = DBSCAN(eps=0.6, min_samples=4)
                iso_labels = iso.fit_predict(X)
                dbs_labels = dbs.fit_predict(X)
                df.loc[subset.index, "anomaly"] = (iso_labels == -1) | (dbs_labels == -1)
            df["skew"] = skew(df["value"])
            df["kurtosis"] = kurtosis(df["value"])
        except Exception as e:
            logger.exception("Anomaly detection failed: %s", e)
        return df

    # -------------------------
    # 3️⃣ Forecasting (Prophet + ARIMA Hybrid)
    # -------------------------
    @staticmethod
    def forecast(df: pd.DataFrame, parameter: str, method: str = "hybrid", periods: int = 30) -> List[Dict[str, Any]]:
        if df.empty or parameter not in df["parameter"].unique():
            return []

        subset = df[df["parameter"] == parameter].groupby("timestamp", as_index=False)["value"].mean()
        subset.rename(columns={"timestamp": "ds", "value": "y"}, inplace=True)
        if len(subset) < 7:
            return []

        try:
            results: List[Dict[str, Any]] = []
            if method in ["prophet", "hybrid"]:
                p = Prophet(daily_seasonality=True)
                p.fit(subset)
                future = p.make_future_dataframe(periods=periods)
                pred = p.predict(future)
                prophet_forecast = pred[["ds", "yhat"]].tail(periods)
            if method in ["arima", "hybrid"]:
                arima = ARIMA(subset["y"], order=(5, 1, 2)).fit()
                arima_fc = arima.forecast(steps=periods)
                arima_df = pd.DataFrame({
                    "ds": [subset["ds"].iloc[-1] + timedelta(days=i) for i in range(1, periods + 1)],
                    "yhat": arima_fc,
                })
            if method == "hybrid":
                merged = pd.merge(prophet_forecast, arima_df, on="ds", suffixes=("_p", "_a"))
                merged["yhat"] = merged[["yhat_p", "yhat_a"]].mean(axis=1)
                results = merged[["ds", "yhat"]].to_dict(orient="records")
            elif method == "prophet":
                results = prophet_forecast.to_dict(orient="records")
            else:
                results = arima_df.to_dict(orient="records")
            return results
        except Exception as e:
            logger.exception("Forecasting failed for parameter %s: %s", parameter, e)
            return []

    # -------------------------
    # 4️⃣ Nonconformity Detection + Cause Assignment
    # -------------------------
    @staticmethod
    def detect_nonconformities(df: pd.DataFrame) -> List[NonConformity]:
        detected = []
        if df.empty:
            return detected

        for _, row in df.iterrows():
            analysis = WaterAnalysis.objects.get(pk=row["analysis_id"])
            parameter_limit = getattr(analysis, f"{row['parameter'].lower()}_limit", None)
            if parameter_limit:
                min_val = float(getattr(parameter_limit, "min_value", 0))
                max_val = float(getattr(parameter_limit, "max_value", 0))
                val = row["value"]
                if val < min_val or val > max_val:
                    deviation = abs(val - (min_val if val < min_val else max_val))
                    nc = NonConformity.objects.create(
                        analysis=analysis,
                        parameter_name=row["parameter"],
                        observed_value=val,
                        min_limit=min_val,
                        max_limit=max_val,
                        deviation=deviation,
                        auto_detected=True,
                        status=NonConformityStatus.OPEN
                    )
                    # Assign likely causes
                    causes = Cause.objects.all()[:2]
                    nc.causes.set(causes)
                    nc.evaluate_risk()
                    detected.append(nc)
        return detected

    # -------------------------
    # 5️⃣ Statistics + PCA + Correlations
    # -------------------------
    @staticmethod
    def generate_statistics(df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty:
            return {}
        try:
            dfv = df["value"]
            slope, intercept, r_value, _, _ = linregress(range(len(dfv)), dfv)
            return {
                "mean": round(dfv.mean(), 3),
                "median": round(dfv.median(), 3),
                "std_dev": round(dfv.std(), 3),
                "variance": round(dfv.var(), 3),
                "min": round(dfv.min(), 3),
                "max": round(dfv.max(), 3),
                "skew": round(skew(dfv), 3),
                "kurtosis": round(kurtosis(dfv), 3),
                "trend_slope": round(slope, 4),
                "r_value": round(r_value, 3),
                "count": len(dfv),
            }
        except Exception as e:
            logger.exception("Statistics generation failed: %s", e)
            return {}

    @staticmethod
    def compound_correlation(df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty:
            return {}
        try:
            pivot = df.pivot_table(index="timestamp", columns=["phase", "parameter"], values="value", aggfunc="mean")
            corr = pivot.corr().round(3)
            cov = pivot.cov().round(3)
            pca = PCA(n_components=min(3, len(pivot.columns)))
            pca.fit(StandardScaler().fit_transform(pivot.fillna(0)))
            return {
                "correlation_matrix": corr.to_dict(),
                "covariance_matrix": cov.to_dict(),
                "pca_variance": pca.explained_variance_ratio_.tolist(),
            }
        except Exception as e:
            logger.exception("Correlation/PCA failed: %s", e)
            return {}

    # -------------------------
    # 6️⃣ PDF Reporting
    # -------------------------
    @staticmethod
    def generate_pdf_report(
        df: pd.DataFrame,
        stats: Dict[str, Any],
        forecast: List[Dict[str, Any]],
        corr: Dict[str, Any],
        parameter: str,
        phase: str
    ) -> io.BytesIO:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
        styles = getSampleStyleSheet()

        content = [
            Paragraph("<b>Quantum QC Analytics Report</b>", styles["Title"]),
            Spacer(1, 12),
            Paragraph(f"Parameter: {parameter}", styles["Normal"]),
            Paragraph(f"Phase: {phase}", styles["Normal"]),
            Spacer(1, 12),
        ]

        # Stats Table
        table_data = [["Metric", "Value"]] + [[k, str(v)] for k, v in stats.items()]
        t = Table(table_data, colWidths=[150, 100])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#004488")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        content.append(t)

        # Forecast
        if forecast:
            plt.figure(figsize=(7, 3))
            plt.plot([f["ds"] for f in forecast], [f["yhat"] for f in forecast], color="darkblue")
            plt.title(f"{parameter} Forecast Projection")
            plt.xticks(rotation=45)
            plt.tight_layout()
            img = io.BytesIO()
            plt.savefig(img, format="png", dpi=150)
            img.seek(0)
            plt.close()
            content.append(Image(img, width=500, height=200))

        # Correlation Heatmap
        if corr.get("correlation_matrix"):
            corr_df = pd.DataFrame(corr["correlation_matrix"])
            plt.figure(figsize=(7, 5))
            sns.heatmap(corr_df, annot=True, fmt=".2f", cmap="coolwarm")
            plt.title("Correlation Heatmap")
            img_corr = io.BytesIO()
            plt.savefig(img_corr, format="png", dpi=150)
            img_corr.seek(0)
            plt.close()
            content.append(Image(img_corr, width=500, height=200))

        doc.build(content)
        buf.seek(0)
        return buf

    # -------------------------
    # 7️⃣ Full Analysis Pipeline
    # -------------------------
    @classmethod
    def analyze(
        cls,
        parameter: Optional[str] = None,
        phase: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        broadcast: bool = True,
    ) -> Dict[str, Any]:
        df = cls.aggregate_results(start, end)
        df = cls.detect_anomalies(df)
        detected_nc = cls.detect_nonconformities(df)
        stats = cls.generate_statistics(df)
        corr = cls.compound_correlation(df)
        forecast = cls.forecast(df, parameter, "hybrid")

        # WebSocket broadcast
        if broadcast and cls.CHANNEL_LAYER:
            group_name = f"qc_dashboard_{parameter}_{phase or 'global'}"
            try:
                async_to_sync(cls.CHANNEL_LAYER.group_send)(
                    group_name,
                    {"type": "qc.update", "content": {"parameter": parameter, "stats": stats, "nonconformities": len(detected_nc), "timestamp": str(now())}},
                )
            except Exception as e:
                logger.exception("WebSocket broadcast failed: %s", e)

        return {"df": df, "stats": stats, "corr": corr, "forecast": forecast, "nonconformities": detected_nc}

# -------------------------
# Celery Task
# -------------------------
@shared_task(name="qc.quantum_analysis_v4_task")
def run_quantum_analysis_task(
    parameter: Optional[str] = None,
    phase: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    engine = QuantumQCAnalyticsEngineV4()
    result = engine.analyze(parameter, phase, start, end)
    pdf_buf = engine.generate_pdf_report(result["df"], result["stats"], result["forecast"], result["corr"], parameter or "", phase or "")
    return {
        "status": "completed",
        "pdf": pdf_buf.getvalue(),
        "timestamp": str(now()),
        "stats": result["stats"],
        "nonconformities": len(result["nonconformities"]),
    }
