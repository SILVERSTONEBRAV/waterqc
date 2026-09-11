# qc_analytics/exports.py
import io
import csv
import json
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from django.http import HttpResponse

from .engine import QCAnalyticsEngine


# ---------------------------------------------------------
# CSV EXPORT (multi-parameter, enhanced)
# ---------------------------------------------------------
def export_csv(request):
    parameters = request.GET.getlist("parameter")
    phase = request.GET.get("phase")
    start = request.GET.get("start")
    end = request.GET.get("end")

    if not parameters:
        return HttpResponse("No parameters specified", status=400)

    response = HttpResponse(content_type="text/csv")
    filename = f"qc_report_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)

    for parameter in parameters:
        df = QCAnalyticsEngine.get_data(parameter, phase, start, end)
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


# ---------------------------------------------------------
# JSON EXPORT (multi-parameter)
# ---------------------------------------------------------
def export_json(request):
    parameters = request.GET.getlist("parameter")
    phase = request.GET.get("phase")
    start = request.GET.get("start")
    end = request.GET.get("end")

    if not parameters:
        return HttpResponse(
            json.dumps({"error": "No parameters specified"}),
            content_type="application/json",
            status=400,
        )

    result = {}
    for parameter in parameters:
        df = QCAnalyticsEngine.get_data(parameter, phase, start, end)
        result[parameter] = df.to_dict(orient="records")

    return HttpResponse(
        json.dumps(result, indent=2),
        content_type="application/json",
    )


# ---------------------------------------------------------
# PDF EXPORT (enhanced multi-chart & correlations)
# ---------------------------------------------------------
def export_pdf(request):
    parameters = request.GET.getlist("parameter")
    phase = request.GET.get("phase")
    start = request.GET.get("start")
    end = request.GET.get("end")

    if not parameters:
        return HttpResponse("No parameters specified", status=400)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = []

    # Report header
    elements.append(Paragraph("<b>Quantum QC Analytical Report</b>", styles["Title"]))
    elements.append(Paragraph(f"Phase: {phase or 'All'}", styles["Normal"]))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # Load all data for correlation if needed
    dfs = []
    for parameter in parameters:
        df = QCAnalyticsEngine.get_data(parameter, phase, start, end)
        if not df.empty:
            dfs.append(df)

    # Iterate over parameters for detailed plots
    for parameter in parameters:
        df = QCAnalyticsEngine.get_data(parameter, phase, start, end)
        stats = QCAnalyticsEngine.generate_statistics(df)

        # Section title
        elements.append(Paragraph(f"<b>Parameter: {parameter}</b>", styles["Heading2"]))
        elements.append(Spacer(1, 6))

        # Stats Table
        table_data = [["Metric", "Value"]] + [[k.capitalize(), str(v)] for k, v in stats.items()]
        table = Table(table_data, colWidths=[150, 100])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 12))

        # Trend Plot
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

    # Correlation heatmap (multi-parameter)
    if dfs and len(dfs) > 1:
        corr_df = QCAnalyticsEngine.compute_multiphase_correlations(dfs)[1]  # correlation_heatmap
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
