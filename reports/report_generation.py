# reports/report_generation.py

import pandas as pd
from datetime import datetime
from io import BytesIO
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from .data_fetching import get_analysis_data


# ============================================================
# 🧠 SAFE DATA NORMALIZER
# ============================================================
def normalize_data(data):
    if data is None:
        return None

    if hasattr(data, "empty") and data.empty:
        return None

    return data


# ============================================================
# 📊 STATISTICAL REPORT
# ============================================================
def generate_statistical_report(analysis_type):
    data = normalize_data(get_analysis_data(analysis_type))

    if data is None:
        return {}

    numeric_only = {}

    try:
        if hasattr(data, "select_dtypes"):
            numeric_data = data.select_dtypes(include="number")
            numeric_only = {
                "mean": numeric_data.mean().to_dict(),
                "median": numeric_data.median().to_dict(),
                "max": numeric_data.max().to_dict(),
                "min": numeric_data.min().to_dict(),
                "std": numeric_data.std().to_dict(),
            }

        elif isinstance(data, dict):
            numeric_only = {
                "summary": data
            }

    except Exception as e:
        return {"error": str(e)}

    return numeric_only


# ============================================================
# 📊 EXCEL REPORT (HTTP RESPONSE)
# ============================================================
def generate_excel_report(analysis_type):
    data = normalize_data(get_analysis_data(analysis_type))

    if data is None:
        return HttpResponse("No data available", status=204)

    buffer = BytesIO()
    safe_name = str(analysis_type).replace(" ", "_").lower()

    try:
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            if hasattr(data, "to_excel"):
                data.to_excel(writer, index=False, sheet_name=safe_name)
            else:
                pd.DataFrame(data).to_excel(writer, index=False, sheet_name=safe_name)

    except Exception as e:
        return HttpResponse(f"Excel generation error: {str(e)}", status=500)

    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{safe_name}_{datetime.now().strftime("%Y%m%d")}.xlsx"'
    )

    return response


# ============================================================
# 📄 PDF REPORT (STRUCTURED)
# ============================================================
def generate_pdf_report(analysis_type):
    data = normalize_data(get_analysis_data(analysis_type))

    if data is None:
        return HttpResponse("No data available", status=204)

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    safe_name = str(analysis_type).replace(" ", "_").lower()

    # Header
    p.setFont("Helvetica-Bold", 14)
    p.drawString(80, height - 50, f"{analysis_type.upper()} REPORT")

    p.setFont("Helvetica", 10)
    p.drawString(80, height - 70, f"Generated: {datetime.now().isoformat()}")

    y = height - 100

    def write(text):
        nonlocal y
        if y < 60:
            p.showPage()
            y = height - 60
        p.drawString(80, y, str(text)[:120])
        y -= 15

    # Data rendering
    if hasattr(data, "iterrows"):
        for _, row in data.iterrows():
            for col in data.columns:
                write(f"{col}: {row[col]}")

    elif isinstance(data, dict):
        for k, v in data.items():
            write(f"{k}: {v}")

    else:
        write(str(data))

    p.save()
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{safe_name}_{datetime.now().strftime("%Y%m%d")}.pdf"'
    )

    return response


# ============================================================
# 🔮 PREDICTIVE REPORT (SAFE PLACEHOLDER)
# ============================================================
def generate_predictive_report(analysis_type):
    data = normalize_data(get_analysis_data(analysis_type))

    if data is None:
        return {
            "analysis_type": analysis_type,
            "prediction": None,
            "confidence": 0.0,
            "message": "No data available",
        }

    return {
        "analysis_type": analysis_type,
        "prediction": "model_not_implemented",
        "confidence": 0.0,
        "generated_at": datetime.now().isoformat(),
    }
