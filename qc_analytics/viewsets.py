import io
import csv
import json
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import seaborn as sns
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors

from django.http import HttpResponse, FileResponse
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from celery.result import AsyncResult

from .engine import QuantumQCAnalyticsEngineV4, run_quantum_analysis_task
from .orchestrator import QuantumQCOrchestrator, schedule_daily_run, schedule_weekly_run, schedule_monthly_run

# Channels 4 channel layer
channel_layer = get_channel_layer()


class QuantumQCAnalyticsViewSet(viewsets.ViewSet):
    """
    ⚡ Quantum QC Analytics (AI-Free, v4)

    Endpoints include:
    - /qc/analytics/run/
    - /qc/analytics/correlation/
    - /qc/analytics/report/
    - /qc/analytics/task-status/
    - /qc/analytics/broadcast/
    - /qc/analytics/compare/
    - /qc/analytics/autopilot/
    - /qc/analytics/export/csv/
    - /qc/analytics/export/json/
    - /qc/analytics/export/pdf/
    - /qc/analytics/orchestrator/run/
    - /qc/analytics/orchestrator/schedule/
    """

    permission_classes = [permissions.IsAuthenticated]

    # -------------------------
    # Helper: Run Engine & Return Standard Payload
    # -------------------------
    def _run_engine(self, parameter=None, phase=None, start=None, end=None, broadcast=True):
        try:
            result = QuantumQCAnalyticsEngineV4.analyze(parameter, phase, start, end, broadcast=broadcast)
            df = result["df"]
            payload = {
                "parameter": parameter,
                "phase": phase,
                "stats": result["stats"],
                "forecast": result["forecast"],
                "correlation": result["corr"],
                "anomalies": df[df.get("anomaly", False)].to_dict(orient="records"),
                "nonconformities": len(result["nonconformities"]),
            }
            return payload, None
        except Exception as e:
            return None, str(e)

    # -------------------------
    # RUN ANALYSIS (SYNC / ASYNC)
    # -------------------------
    @action(detail=False, methods=["post"], url_path="run")
    def run_analysis(self, request):
        data = request.data
        parameter = data.get("parameter")
        phase = data.get("phase")
        start = data.get("start")
        end = data.get("end")
        mode = data.get("mode", "sync")

        try:
            start_date = datetime.strptime(start, "%Y-%m-%d") if start else None
            end_date = datetime.strptime(end, "%Y-%m-%d") if end else None
        except Exception:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

        if mode == "async":
            task = run_quantum_analysis_task.delay(parameter, phase, start, end)
            return Response({"task_id": task.id, "status": "queued"}, status=status.HTTP_202_ACCEPTED)

        payload, error = self._run_engine(parameter, phase, start_date, end_date)
        if error:
            return Response({"error": error}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Channels 4: broadcast safely
        async_to_sync(channel_layer.group_send)(
            f"qc_dashboard_{parameter}_{phase or 'global'}",
            {"type": "qc.update", "content": payload},
        )
        return Response(payload, status=status.HTTP_200_OK)

    # -------------------------
    # CORRELATION + PCA
    # -------------------------
    @action(detail=False, methods=["get"], url_path="correlation")
    def correlation_analysis(self, request):
        df = QuantumQCAnalyticsEngineV4.aggregate_results(
            request.query_params.get("start"),
            request.query_params.get("end"),
        )
        result = QuantumQCAnalyticsEngineV4.compound_correlation(df)
        return Response(result, status=status.HTTP_200_OK)

    # -------------------------
    # PDF REPORT GENERATOR
    # -------------------------
    @action(detail=False, methods=["get"], url_path="report")
    def generate_report(self, request):
        parameter = request.query_params.get("parameter")
        phase = request.query_params.get("phase")
        start = request.query_params.get("start")
        end = request.query_params.get("end")

        payload, error = self._run_engine(parameter, phase, start, end, broadcast=False)
        if error:
            return Response({"error": error}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            pdf_buf = QuantumQCAnalyticsEngineV4.generate_pdf_report(
                payload.get("df"), payload["stats"], payload["forecast"], payload["correlation"],
                parameter or "", phase or ""
            )
            return FileResponse(pdf_buf, as_attachment=True, filename=f"Quantum_QC_{parameter}_{phase}.pdf")
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------------
    # BROADCAST
    # -------------------------
    @action(detail=False, methods=["post"], url_path="broadcast")
    def broadcast(self, request):
        payload = request.data
        async_to_sync(channel_layer.group_send)(
            "qc_dashboard", {"type": "qc.update", "content": payload}
        )
        return Response({"status": "broadcasted", "payload": payload})

    # -------------------------
    # MULTI-PARAMETER COMPARISON
    # -------------------------
    @action(detail=False, methods=["post"], url_path="compare")
    def compare_parameters(self, request):
        params = request.data.get("parameters", [])
        phase = request.data.get("phase")
        start = request.data.get("start")
        end = request.data.get("end")

        results = {}
        for p in params:
            payload, error = self._run_engine(p, phase, start, end, broadcast=False)
            results[p] = payload["stats"] if payload else {"error": error}

        return Response({"comparative_stats": results}, status=status.HTTP_200_OK)

    # -------------------------
    # ASYNC TASK STATUS
    # -------------------------
    @action(detail=False, methods=["get"], url_path="task-status")
    def task_status(self, request):
        task_id = request.query_params.get("task_id")
        if not task_id:
            return Response({"error": "Missing task_id"}, status=status.HTTP_400_BAD_REQUEST)
        task = AsyncResult(task_id)
        return Response(
            {"status": "completed", "result": task.get()} if task.ready() else {"status": task.status},
            status=status.HTTP_200_OK
        )

    # -------------------------
    # AUTO-PILOT MODE
    # -------------------------
    @action(detail=False, methods=["post"], url_path="autopilot")
    def autopilot(self, request):
        mode = request.data.get("mode", "daily")
        parameter = request.data.get("parameter")
        phase = request.data.get("phase")

        now_dt = datetime.now()
        start = {
            "daily": (now_dt - timedelta(days=1)).strftime("%Y-%m-%d"),
            "weekly": (now_dt - timedelta(days=7)).strftime("%Y-%m-%d"),
            "monthly": (now_dt - timedelta(days=30)).strftime("%Y-%m-%d"),
        }.get(mode, (now_dt - timedelta(days=1)).strftime("%Y-%m-%d"))
        end = now_dt.strftime("%Y-%m-%d")

        payload, error = self._run_engine(parameter, phase, start, end)
        if error:
            return Response({"error": error}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        async_to_sync(channel_layer.group_send)(
            f"qc_dashboard_{parameter}_{phase or 'global'}",
            {"type": "qc.update", "content": {"mode": mode, "data": payload}},
        )

        return Response({"autopilot": mode, "stats": payload["stats"], "nonconformities": payload["nonconformities"]})

    # -------------------------
    # EXPORT ENDPOINTS (CSV / JSON / PDF)
    # -------------------------
    @action(detail=False, methods=["get"], url_path="export/csv")
    def export_csv(self, request):
        parameters = request.query_params.getlist("parameter")
        phase = request.query_params.get("phase")
        start = request.query_params.get("start")
        end = request.query_params.get("end")

        if not parameters:
            return Response({"error": "No parameters specified"}, status=400)

        response = HttpResponse(content_type="text/csv")
        filename = f"qc_report_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)

        for parameter in parameters:
            df = QuantumQCAnalyticsEngineV4.get_data(parameter, phase, start, end)
            writer.writerow([f"Parameter: {parameter}", f"Phase: {phase or 'All'}"])
            if df.empty:
                writer.writerow(["No data available"])
                writer.writerow([])
                continue
            writer.writerow(df.columns)
            for _, row in df.iterrows():
                writer.writerow(row)
            writer.writerow([])

        return response

    @action(detail=False, methods=["get"], url_path="export/json")
    def export_json(self, request):
        parameters = request.query_params.getlist("parameter")
        phase = request.query_params.get("phase")
        start = request.query_params.get("start")
        end = request.query_params.get("end")

        if not parameters:
            return Response({"error": "No parameters specified"}, status=400)

        result = {}
        for parameter in parameters:
            df = QuantumQCAnalyticsEngineV4.get_data(parameter, phase, start, end)
            result[parameter] = df.to_dict(orient="records")

        return HttpResponse(json.dumps(result, indent=2), content_type="application/json")

    @action(detail=False, methods=["get"], url_path="export/pdf")
    def export_pdf(self, request):
        parameters = request.query_params.getlist("parameter")
        phase = request.query_params.get("phase")
        start = request.query_params.get("start")
        end = request.query_params.get("end")

        if not parameters:
            return Response({"error": "No parameters specified"}, status=400)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("<b>Quantum QC Analytical Report</b>", styles["Title"]))
        elements.append(Paragraph(f"Phase: {phase or 'All'}", styles["Normal"]))
        elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
        elements.append(Spacer(1, 12))

        dfs = []
        for parameter in parameters:
            df = QuantumQCAnalyticsEngineV4.get_data(parameter, phase, start, end)
            dfs.append(df)
            stats = QuantumQCAnalyticsEngineV4.generate_statistics(df)

            elements.append(Paragraph(f"<b>Parameter: {parameter}</b>", styles["Heading2"]))
            elements.append(Spacer(1, 6))

            table_data = [["Metric", "Value"]] + [[k.capitalize(), str(v)] for k, v in stats.items()]
            table = Table(table_data, colWidths=[150, 100])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 12))

            if not df.empty:
                plt.figure(figsize=(6, 3))
                df_grouped = df.groupby("timestamp")["value"].mean().reset_index()
                plt.plot(df_grouped["timestamp"], df_grouped["value"], marker="o", color="navy", label="Trend")
                if "anomaly" in df.columns:
                    anomalies = df_grouped[df_grouped["value"].isin(df[df["anomaly"]]["value"])]
                    plt.scatter(anomalies["timestamp"], anomalies["value"], color="red", label="Anomaly", zorder=5)
                plt.title(f"{parameter} Trend ({phase or 'All'})")
                plt.xlabel("Timestamp")
                plt.ylabel("Value")
                plt.legend()
                plt.tight_layout()
                img_buffer = io.BytesIO()
                plt.savefig(img_buffer, format="PNG")
                plt.close()
                img_buffer.seek(0)
                elements.append(Image(img_buffer, width=500, height=200))
                elements.append(Spacer(1, 12))

        if dfs and len(dfs) > 1:
            corr_df = QuantumQCAnalyticsEngineV4.compute_multiphase_correlations(dfs)[1]
            if corr_df is not None:
                plt.figure(figsize=(6, 4))
                sns.heatmap(corr_df, annot=True, fmt=".2f", cmap="coolwarm")
                plt.title("Multi-Parameter Correlation Heatmap")
                plt.tight_layout()
                img_corr = io.BytesIO()
                plt.savefig(img_corr, format="PNG")
                plt.close()
                img_corr.seek(0)
                elements.append(Image(img_corr, width=500, height=200))
                elements.append(Spacer(1, 12))

        doc.build(elements)
        buffer.seek(0)
        return HttpResponse(buffer, content_type="application/pdf")

    # -------------------------
    # ORCHESTRATOR ENDPOINTS
    # -------------------------
    @action(detail=False, methods=["post"], url_path="orchestrator/run")
    def run_orchestrator(self, request):
        data = request.data
        parameters = data.get("parameters")
        phases = data.get("phases")
        mode = data.get("mode", "daily")

        result = QuantumQCOrchestrator.run(
            parameters=parameters,
            phases=phases,
            mode=mode,
        )
        return Response(result, status=200)

    @action(detail=False, methods=["post"], url_path="orchestrator/schedule")
    def schedule_orchestrator(self, request):
        mode = request.data.get("mode", "daily")
        if mode == "daily":
            task = schedule_daily_run.delay()
        elif mode == "weekly":
            task = schedule_weekly_run.delay()
        elif mode == "monthly":
            task = schedule_monthly_run.delay()
        else:
            return Response({"error": "Invalid mode"}, status=400)

        return Response({"status": "scheduled", "mode": mode, "task_id": task.id}, status=202)
