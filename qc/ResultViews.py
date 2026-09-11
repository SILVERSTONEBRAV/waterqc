# qc/ResultViews.py

from django.views.generic import TemplateView

from core.mixins import WanjalaMixin
from qc.services.worksheet_service import WorksheetService


class AnalysisWorksheetView(
    WanjalaMixin,
    TemplateView,
):
    """
    Water Analysis Worksheet.

    All worksheet construction is delegated to
    WorksheetService.
    """

    template_name = "qc/analysis/worksheet.html"

    permission_required_view = (
        "qc.view_wateranalysis"
    )

    def get_context_data(
        self,
        **kwargs,
    ):
        context = super().get_context_data(
            **kwargs
        )

        context.update(
            WorksheetService.for_request(
                self.request
            )
        )

        return context