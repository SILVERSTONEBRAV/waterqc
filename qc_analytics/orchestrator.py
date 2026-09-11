# qc_analytics/orchestrator.py
import io
import json
from datetime import datetime, timedelta
from typing import List, Optional

from celery import shared_task, chord
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .tasks import run_quantum_analysis_task
from .engine import QuantumQCAnalyticsEngineV4

channel_layer = get_channel_layer()


class QuantumQCOrchestrator:
    """
    Advanced orchestrator for Quantum QC analytics tasks.

    Features:
        - Multi-parameter, multi-phase batch execution
        - Daily, weekly, monthly auto-scheduling
        - AI-driven summaries & anomaly detection
        - Real-time WebSocket dashboard updates
        - PDF/JSON automatic reporting
        - Resilient: skips empty datasets
    """

    @classmethod
    def get_schedule_dates(cls, mode: str = "daily") -> (str, str):
        """Return dynamic start/end dates for daily/weekly/monthly runs."""
        now_dt = datetime.now()
        start = {
            "daily": (now_dt - timedelta(days=1)).strftime("%Y-%m-%d"),
            "weekly": (now_dt - timedelta(days=7)).strftime("%Y-%m-%d"),
            "monthly": (now_dt - timedelta(days=30)).strftime("%Y-%m-%d"),
        }.get(mode, (now_dt - timedelta(days=1)).strftime("%Y-%m-%d"))
        end = now_dt.strftime("%Y-%m-%d")
        return start, end

    @classmethod
    def broadcast_message(cls, message: dict, group: str = "qc_dashboard"):
        """Send a real-time message to a WebSocket group."""
        async_to_sync(channel_layer.group_send)(
            group,
            {"type": "qc.update", "content": message},
        )

    @classmethod
    def run(
        cls,
        parameters: Optional[List[str]] = None,
        phases: Optional[List[str]] = None,
        mode: str = "daily",
        forecast_method: str = "hybrid",
        periods: int = 30,
        generate_pdf: bool = True,
        generate_json: bool = True,
    ):
        """Orchestrate a batch QC analytics execution with automatic reporting."""
        start, end = cls.get_schedule_dates(mode)

        # Fetch all parameters if none specified
        if parameters is None:
            df_all = QuantumQCAnalyticsEngine.get_data()
            parameters = df_all.parameter.unique().tolist() if not df_all.empty else []

        # Fetch all phases if none specified
        if phases is None:
            phases = list(QuantumQCAnalyticsEngine.PHASE_MODELS.keys())

        # Create task signatures for all parameter-phase combinations
        task_signatures = [
            run_quantum_analysis_task.s(
                parameters=[param],
                phases=[phase],
                start=start,
                end=end,
                forecast_method=forecast_method,
                periods=periods,
                generate_pdf=generate_pdf,
                generate_json=generate_json,
            )
            for param in parameters
            for phase in phases
        ]

        if not task_signatures:
            cls.broadcast_message({"status": "no_tasks", "message": "No parameters or phases found."})
            return {"status": "no_tasks"}

        # Execute tasks in a chord, aggregate results in post_process
        workflow = chord(task_signatures)(cls.post_process.s(mode, generate_pdf, generate_json))
        cls.broadcast_message(
            {"status": "scheduled", "message": f"{len(task_signatures)} tasks scheduled."}
        )
        return {"status": "scheduled", "task_count": len(task_signatures)}

    @staticmethod
    @shared_task(name="qc.orchestrator.post_process")
    def post_process(results, mode, generate_pdf, generate_json):
        """Aggregate task results, generate summaries, and broadcast to dashboard."""
        combined_summary = []
        pdf_buffers = []
        json_exports = []

        for res in results:
            if not res.get("results"):
                continue
            for r in res["results"]:
                combined_summary.append({
                    "parameter": r.get("parameter"),
                    "phase": r.get("phase"),
                    "ai_summary": r.get("ai_summary"),
                    "stats": r.get("stats"),
                })
            if generate_pdf:
                pdf_buffers.extend(res.get("pdf_reports", []))
            if generate_json:
                json_exports.append(res.get("json_export"))

        summary_payload = {
            "mode": mode,
            "summary_count": len(combined_summary),
            "summary": combined_summary,
            "pdf_reports_count": len(pdf_buffers),
            "json_exports_count": len(json_exports),
            "timestamp": datetime.now().isoformat()
        }

        QuantumQCOrchestrator.broadcast_message(summary_payload)
        return summary_payload


# ==========================================================
# 🔹 Celery Beat Integration Examples
# ==========================================================
@shared_task(name="qc.orchestrator.schedule_daily_run")
def schedule_daily_run():
    return QuantumQCOrchestrator.run(mode="daily")


@shared_task(name="qc.orchestrator.schedule_weekly_run")
def schedule_weekly_run():
    return QuantumQCOrchestrator.run(mode="weekly")


@shared_task(name="qc.orchestrator.schedule_monthly_run")
def schedule_monthly_run():
    return QuantumQCOrchestrator.run(mode="monthly")
