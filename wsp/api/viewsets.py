from __future__ import annotations

from rest_framework import viewsets, permissions, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend

from ..models import (
    Category, ThematicArea, ThematicGroup,
    OperationalUnit, Survey, Question, Option,
    Response as SurveyResponse,
    ResponseHistory, DashboardWidgetLayout
)
from .serializers import (
    CategorySerializer, ThematicAreaSerializer, ThematicGroupSerializer,
    OperationalUnitSerializer, SurveySerializer,
    QuestionSerializer, OptionSerializer,
    ResponseSerializer, ResponseHistorySerializer,
    DashboardWidgetLayoutSerializer
)

# --------------------------------------------------------------------
# Generic Base ViewSet
# --------------------------------------------------------------------
class BaseActiveViewSet(viewsets.ModelViewSet):
    """
    Common behaviour:
      * Only return is_active=True by default.
      * Adds search/filter support.
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields: list[str] = []
    ordering_fields: list[str] = ["created_at", "updated_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(is_active=True)


# --------------------------------------------------------------------
# Core Domain
# --------------------------------------------------------------------
class OptionViewSet(BaseActiveViewSet):
    queryset = Option.objects.all()
    serializer_class = OptionSerializer
    search_fields = ["text"]


class QuestionViewSet(BaseActiveViewSet):
    queryset = Question.objects.all().prefetch_related("options")
    serializer_class = QuestionSerializer
    search_fields = ["text"]


class ThematicAreaViewSet(BaseActiveViewSet):
    queryset = ThematicArea.objects.all().prefetch_related("questions__options")
    serializer_class = ThematicAreaSerializer
    search_fields = ["name"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        survey_id = self.request.query_params.get("survey")
        if survey_id:
            ctx["survey"] = Survey.objects.filter(pk=survey_id).first()
        return ctx


class CategoryViewSet(BaseActiveViewSet):
    queryset = Category.objects.all().prefetch_related("areas__questions__options")
    serializer_class = CategorySerializer
    search_fields = ["name"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        survey_id = self.request.query_params.get("survey")
        if survey_id:
            ctx["survey"] = Survey.objects.filter(pk=survey_id).first()
        return ctx


class ThematicGroupViewSet(BaseActiveViewSet):
    queryset = ThematicGroup.objects.all().prefetch_related("areas__questions__options")
    serializer_class = ThematicGroupSerializer
    search_fields = ["name"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        survey_id = self.request.query_params.get("survey")
        if survey_id:
            ctx["survey"] = Survey.objects.filter(pk=survey_id).first()
        return ctx


class OperationalUnitViewSet(BaseActiveViewSet):
    queryset = OperationalUnit.objects.all()
    serializer_class = OperationalUnitSerializer
    search_fields = ["name"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        survey_id = self.request.query_params.get("survey")
        if survey_id:
            ctx["survey"] = Survey.objects.filter(pk=survey_id).first()
        return ctx


# --------------------------------------------------------------------
# Survey & Responses
# --------------------------------------------------------------------
class SurveyViewSet(BaseActiveViewSet):
    queryset = Survey.objects.all().select_related("unit")
    serializer_class = SurveySerializer
    search_fields = ["name", "slug"]

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        """
        Custom endpoint: return hierarchical report JSON.
        """
        survey = self.get_object()
        return Response(survey.hierarchical_report())


class ResponseViewSet(BaseActiveViewSet):
    queryset = SurveyResponse.objects.select_related(
        "survey", "question", "self_option", "supervisor_option"
    )
    serializer_class = ResponseSerializer
    filterset_fields = ["survey", "question", "respondent", "supervisor"]


class ResponseHistoryViewSet(BaseActiveViewSet):
    queryset = ResponseHistory.objects.select_related("response", "survey", "question")
    serializer_class = ResponseHistorySerializer
    filterset_fields = ["survey", "question", "user"]


# --------------------------------------------------------------------
# Dashboard Layout
# --------------------------------------------------------------------
class DashboardWidgetLayoutViewSet(BaseActiveViewSet):
    """
    Allows each user to store their dashboard gridstack layout.
    """
    serializer_class = DashboardWidgetLayoutSerializer

    def get_queryset(self):
        return DashboardWidgetLayout.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
