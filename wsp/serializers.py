from __future__ import annotations
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import (
    Category, ThematicArea, ThematicGroup,
    OperationalUnit, Survey, Question, Option,
    Response, ResponseHistory, DashboardWidgetLayout
)

User = get_user_model()


# ---------- Base ----------
class BaseUUIDSerializer(serializers.ModelSerializer):
    """Expose common audit fields."""
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    meta = serializers.JSONField(read_only=True)

    class Meta:
        fields = ["id", "created_at", "updated_at", "is_active", "meta"]
        abstract = True


# ---------- Core Domain ----------
class OptionSerializer(BaseUUIDSerializer):
    question_id = serializers.UUIDField(source="question.id", read_only=True)

    class Meta(BaseUUIDSerializer.Meta):
        model = Option
        fields = BaseUUIDSerializer.Meta.fields + [
            "question", "question_id", "text", "score", "color"
        ]


class QuestionSerializer(BaseUUIDSerializer):
    options = OptionSerializer(many=True, read_only=True)
    thematic_area_id = serializers.UUIDField(source="thematic_area.id", read_only=True)

    class Meta(BaseUUIDSerializer.Meta):
        model = Question
        fields = BaseUUIDSerializer.Meta.fields + [
            "thematic_area", "thematic_area_id", "text", "weight", "options"
        ]


class ThematicAreaSerializer(BaseUUIDSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    total_score = serializers.SerializerMethodField()
    average_score = serializers.SerializerMethodField()
    category_id = serializers.UUIDField(source="category.id", read_only=True)

    class Meta(BaseUUIDSerializer.Meta):
        model = ThematicArea
        fields = BaseUUIDSerializer.Meta.fields + [
            "category", "category_id", "name", "slug",
            "total_score", "average_score", "questions"
        ]

    def get_total_score(self, obj) -> Decimal:
        survey = self.context.get("survey")
        return obj.total_score(survey)

    def get_average_score(self, obj) -> Decimal:
        survey = self.context.get("survey")
        return obj.average_score(survey)


class CategorySerializer(BaseUUIDSerializer):
    areas = ThematicAreaSerializer(many=True, read_only=True)
    total_score = serializers.SerializerMethodField()
    average_score = serializers.SerializerMethodField()
    survey_id = serializers.UUIDField(source="survey.id", read_only=True)

    class Meta(BaseUUIDSerializer.Meta):
        model = Category
        fields = BaseUUIDSerializer.Meta.fields + [
            "name", "slug", "areas", "total_score", "average_score", "survey_id"
        ]

    def get_total_score(self, obj) -> Decimal:
        survey = self.context.get("survey")
        return obj.total_score(survey)

    def get_average_score(self, obj) -> Decimal:
        survey = self.context.get("survey")
        return obj.average_score(survey)


class ThematicGroupSerializer(BaseUUIDSerializer):
    areas = ThematicAreaSerializer(many=True, read_only=True)
    total_score = serializers.SerializerMethodField()
    average_score = serializers.SerializerMethodField()
    thematic_area_id = serializers.UUIDField(source="thematic_area.id", read_only=True)

    class Meta(BaseUUIDSerializer.Meta):
        model = ThematicGroup
        fields = BaseUUIDSerializer.Meta.fields + [
            "name", "areas", "total_score", "average_score", "thematic_area_id"
        ]

    def get_total_score(self, obj) -> Decimal:
        survey = self.context.get("survey")
        return obj.total_score(survey)

    def get_average_score(self, obj) -> Decimal:
        survey = self.context.get("survey")
        return obj.average_score(survey)


class OperationalUnitSerializer(BaseUUIDSerializer):
    total_score = serializers.SerializerMethodField()
    average_score = serializers.SerializerMethodField()

    class Meta(BaseUUIDSerializer.Meta):
        model = OperationalUnit
        fields = BaseUUIDSerializer.Meta.fields + [
            "name", "slug", "total_score", "average_score"
        ]

    def get_total_score(self, obj) -> Decimal:
        survey = self.context.get("survey")
        return obj.total_score(survey)

    def get_average_score(self, obj) -> Decimal:
        survey = self.context.get("survey")
        return obj.average_score(survey)


class SurveySerializer(BaseUUIDSerializer):
    unit = serializers.StringRelatedField()
    unit_id = serializers.UUIDField(source="unit.id", read_only=True)
    total_score = serializers.SerializerMethodField()
    hierarchical_report = serializers.SerializerMethodField()

    class Meta(BaseUUIDSerializer.Meta):
        model = Survey
        fields = BaseUUIDSerializer.Meta.fields + [
            "unit", "unit_id", "name", "slug", "start_date", "end_date",
            "share_state", "share_uuid", "share_expires_at",
            "average_score", "total_score", "hierarchical_report"
        ]

    def get_total_score(self, obj) -> Decimal:
        return obj.total_score()

    def get_hierarchical_report(self, obj):
        return obj.hierarchical_report()


# ---------- Responses ----------
class ResponseSerializer(BaseUUIDSerializer):
    average_score = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )
    survey_id = serializers.UUIDField(source="survey.id", read_only=True)
    question_id = serializers.UUIDField(source="question.id", read_only=True)

    class Meta(BaseUUIDSerializer.Meta):
        model = Response
        fields = BaseUUIDSerializer.Meta.fields + [
            "survey", "survey_id", "question", "question_id",
            "self_option", "supervisor_option",
            "respondent", "supervisor",
            "completed_at", "average_score"
        ]


class ResponseHistorySerializer(BaseUUIDSerializer):
    survey_id = serializers.UUIDField(source="survey.id", read_only=True)
    question_id = serializers.UUIDField(source="question.id", read_only=True)

    class Meta(BaseUUIDSerializer.Meta):
        model = ResponseHistory
        fields = BaseUUIDSerializer.Meta.fields + [
            "response", "survey", "survey_id", "question", "question_id",
            "self_option", "supervisor_option",
            "user", "changed_at"
        ]


# ---------- Dashboard Layout ----------
class DashboardWidgetLayoutSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(slug_field="username", read_only=True)

    class Meta:
        model = DashboardWidgetLayout
        fields = [
            "id", "user", "unit", "widget_name",
            "x", "y", "width", "height",
            "collapsed", "updated_at"
        ]
        read_only_fields = ["id", "updated_at"]
