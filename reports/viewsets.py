# reports/viewsets.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    DailyReport,
    WeeklyReport,
    MonthlyReport,
    AnnualReport,
    CustomDateRangeReport,
)

from .serializers import (
    DailyReportSerializer,
    WeeklyReportSerializer,
    MonthlyReportSerializer,
    AnnualReportSerializer,
    CustomDateRangeReportSerializer,
)

from .report_generation import (
    generate_statistical_report,
    generate_excel_report,
    generate_pdf_report,
    generate_predictive_report,
)


# ============================================================
# 📊 BASE REPORT VIEWSET
# ============================================================
class ReportViewSet(viewsets.ModelViewSet):

    def _get_analysis_type(self, request, pk):
        analysis_type = request.query_params.get("analysis_type")

        if not analysis_type:
            # fallback: use model name
            return self.queryset.model.__name__.replace("Report", "").lower()

        return analysis_type

    # ========================================================
    # 📊 STATISTICS
    # ========================================================
    @action(detail=True, methods=["get"], url_path="statistics")
    def generate_statistics(self, request, pk=None):
        analysis_type = self._get_analysis_type(request, pk)
        data = generate_statistical_report(analysis_type)
        return Response(data, status=status.HTTP_200_OK)

    # ========================================================
    # 📄 EXCEL
    # ========================================================
    @action(detail=True, methods=["get"], url_path="excel")
    def generate_excel(self, request, pk=None):
        analysis_type = self._get_analysis_type(request, pk)
        return generate_excel_report(analysis_type)

    # ========================================================
    # 📄 PDF
    # ========================================================
    @action(detail=True, methods=["get"], url_path="pdf")
    def generate_pdf(self, request, pk=None):
        analysis_type = self._get_analysis_type(request, pk)
        return generate_pdf_report(analysis_type)

    # ========================================================
    # 🔮 PREDICTIVE
    # ========================================================
    @action(detail=True, methods=["get"], url_path="predictive")
    def generate_predictive(self, request, pk=None):
        analysis_type = self._get_analysis_type(request, pk)
        data = generate_predictive_report(analysis_type)
        return Response(data, status=status.HTTP_200_OK)
