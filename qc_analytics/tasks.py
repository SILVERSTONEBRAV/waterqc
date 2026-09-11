# qc_analytics/tasks.py
import io
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from celery import shared_task, Task
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from .engine import QuantumQCAnalyticsEngineV4

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
channel_layer = get_channel_layer()


# =============================================================
# ⚡ Base Celery Task with WebSocket Progress & Retries
# =============================================================
class QuantumQCBaseTask(Task):
    """Base Celery task for Quantum QC Analytics with progress streaming and retries."""
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_kwargs = {"max_retries": 5, "countdown": 15}

    def update_progress(self, percent: int, message: str = None):
        async_to_sync(channel_layer.group_send)(
            "qc_analytics",
            {"type": "analytics.progress", "data": {"percent": percent, "message": message}},
        )


# =============================================================
# 🧩 Advanced Batch Analytics Task
# =============================================================
@shared_task(bind=True, base=QuantumQCBaseTask, name="qc.run_quantum_batch_task")
def run_quantum_analysis_task(
    self,
    parameters: List[str] = None,
    phases: List[str] = None,
    start: str = None,
    end: str = None,
    forecast_method: str = "hybrid",
    periods: int = 30,
    generate_pdf: bool = True,
    generate_json: bool = False,
) -> Dict[str, Any]:
    """
    Advanced batch analytics task for Quantum QC Engine.

    Features:
    - Multi-parameter & multi-phase analytics
    - Hybrid anomaly detection
    - Forecasting (Prophet + ARIMA hybrid)
    - Correlation, PCA
    - Statistics generation
    - Nonconformity detection
    - PDF & JSON export
    - WebSocket progress updates
    """
    try:
        # -------------------------
        # Parse dates
        # -------------------------
        start_date = datetime.strptime(start, "%Y-%m-%d") if start else None
        end_date = datetime.strptime(end, "%Y-%m-%d") if end else None
        if parameters is None:
            parameters = []
        if phases is None:
            phases = list(QuantumQCAnalyticsEngineV4.PHASE_MODELS.keys())

        total_tasks = max(len(parameters) * len(phases), 1)
        completed = 0
        results: List[Dict[str, Any]] = []

        # -------------------------
        # Loop through parameters & phases
        # -------------------------
        for param in parameters:
            for phase in phases:
                self.update_progress(int((completed / total_tasks) * 100), f"Processing {param} ({phase})")

                df = QuantumQCAnalyticsEngineV4.aggregate_results(start_date, end_date)
                df = QuantumQCAnalyticsEngineV4.detect_anomalies(df)
                stats = QuantumQCAnalyticsEngineV4.generate_statistics(df)
                forecast = QuantumQCAnalyticsEngineV4.forecast(df, param, forecast_method, periods)
                corr = QuantumQCAnalyticsEngineV4.compound_correlation(df)
                nonconformities = QuantumQCAnalyticsEngineV4.detect_nonconformities(df)

                result_item = {
                    "parameter": param,
                    "phase": phase,
                    "stats": stats,
                    "forecast": forecast,
                    "anomalies": df[df.get("anomaly", False)].to_dict(orient="records"),
                    "correlations": corr,
                    "nonconformities": [nc.id for nc in nonconformities],
                }
                results.append(result_item)

                # Broadcast to WebSocket dashboards
                async_to_sync(channel_layer.group_send)(
                    "qc_analytics",
                    {"type": "analytics.update", "data": result_item},
                )
                completed += 1

        self.update_progress(100, "All analytics completed.")

        # -------------------------
        # PDF Report Generation
        # -------------------------
        pdf_reports: List[bytes] = []
        if generate_pdf:
            for res in results:
                buf = io.BytesIO()
                doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
                styles = getSampleStyleSheet()
                content = [
                    Paragraph(f"<b>Quantum QC Report: {res['parameter']} ({res['phase']})</b>", styles["Title"]),
                    Spacer(1, 12)
                ]

                # Stats table
                table_data = [["Metric", "Value"]] + [[k, str(v)] for k, v in res["stats"].items()]
                table = Table(table_data, colWidths=[150, 100])
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#004488")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ]))
                content.append(table)
                content.append(Spacer(1, 12))

                # Forecast chart
                if res["forecast"]:
                    plt.figure(figsize=(8, 3))
                    plt.plot([f["ds"] for f in res["forecast"]], [f["yhat"] for f in res["forecast"]], color="darkblue")
                    plt.title(f"{res['parameter']} Forecast Trend")
                    plt.xticks(rotation=45)
                    plt.tight_layout()
                    img_buf = io.BytesIO()
                    plt.savefig(img_buf, format="png", dpi=150)
                    plt.close()
                    img_buf.seek(0)
                    content.append(Image(img_buf, width=500, height=200))

                # Correlation heatmap
                if res["correlations"].get("correlation_matrix"):
                    corr_df = pd.DataFrame(res["correlations"]["correlation_matrix"])
                    plt.figure(figsize=(7, 5))
                    sns.heatmap(corr_df, annot=True, fmt=".2f", cmap="coolwarm")
                    plt.title(f"{res['parameter']} Correlation Heatmap")
                    img_corr = io.BytesIO()
                    plt.savefig(img_corr, format="png", dpi=150)
                    plt.close()
                    img_corr.seek(0)
                    content.append(Image(img_corr, width=500, height=200))

                doc.build(content)
                buf.seek(0)
                pdf_reports.append(buf.getvalue())

        # -------------------------
        # Optional JSON Export
        # -------------------------
        json_export = json.dumps(results, default=str) if generate_json else None

        return {
            "status": "completed",
            "summary": f"{len(parameters)} parameters × {len(phases)} phases analyzed",
            "results": results,
            "pdf_reports": pdf_reports,
            "json_export": json_export,
        }

    except Exception as e:
        logger.exception("Quantum QC batch task failed: %s", e)
        self.retry(exc=e)
