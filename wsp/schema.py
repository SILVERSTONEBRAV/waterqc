# wsp/schema.py
import graphene
from graphene import relay
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from django.db import transaction
from django.db.models import Prefetch, Sum, Avg, F, FloatField
from graphql import GraphQLError
from decimal import Decimal

from .models import (
    Category,
    ThematicArea,
    ThematicGroup,
    OperationalUnit,
    Survey,
    Question,
    Option,
    Response,
)
from django.contrib.auth import get_user_model

User = get_user_model()

# ==============================================================================
# OBJECT TYPES
# ==============================================================================

class UserType(DjangoObjectType):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name")
        interfaces = (relay.Node,)


class OptionType(DjangoObjectType):
    class Meta:
        model = Option
        fields = ("id", "text", "score", "color")
        interfaces = (relay.Node,)


class QuestionType(DjangoObjectType):
    options = graphene.List(OptionType)

    class Meta:
        model = Question
        fields = ("id", "text", "weight", "thematic_area")
        interfaces = (relay.Node,)

    def resolve_options(self, info):
        return self.options.all()


class ThematicAreaType(DjangoObjectType):
    questions = graphene.List(QuestionType)
    total_score = graphene.Float(survey_id=graphene.ID(required=False))
    average_score = graphene.Float(survey_id=graphene.ID(required=False))

    class Meta:
        model = ThematicArea
        fields = ("id", "name", "slug", "category")
        interfaces = (relay.Node,)

    def resolve_questions(self, info):
        return self.questions.all()

    def resolve_total_score(self, info, survey_id=None):
        survey = Survey.objects.filter(pk=survey_id).first() if survey_id else None
        return float(self.total_score(survey))

    def resolve_average_score(self, info, survey_id=None):
        survey = Survey.objects.filter(pk=survey_id).first() if survey_id else None
        return float(self.average_score(survey))


class CategoryType(DjangoObjectType):
    areas = graphene.List(ThematicAreaType)
    total_score = graphene.Float(survey_id=graphene.ID(required=False))
    average_score = graphene.Float(survey_id=graphene.ID(required=False))

    class Meta:
        model = Category
        fields = ("id", "name", "slug")
        interfaces = (relay.Node,)

    def resolve_areas(self, info):
        return self.areas.all()

    def resolve_total_score(self, info, survey_id=None):
        survey = Survey.objects.filter(pk=survey_id).first() if survey_id else None
        return float(self.total_score(survey))

    def resolve_average_score(self, info, survey_id=None):
        survey = Survey.objects.filter(pk=survey_id).first() if survey_id else None
        return float(self.average_score(survey))


class ThematicGroupType(DjangoObjectType):
    areas = graphene.List(ThematicAreaType)

    class Meta:
        model = ThematicGroup
        fields = ("id", "name")
        interfaces = (relay.Node,)

    def resolve_areas(self, info):
        return self.areas.all()


class OperationalUnitType(DjangoObjectType):
    surveys = graphene.List(lambda: SurveyType)

    class Meta:
        model = OperationalUnit
        fields = ("id", "name", "slug")
        interfaces = (relay.Node,)

    def resolve_surveys(self, info):
        return self.surveys.all().prefetch_related("responses__question__thematic_area")


class ResponseType(DjangoObjectType):
    average_score = graphene.Float()

    class Meta:
        model = Response
        fields = (
            "id",
            "survey",
            "question",
            "self_option",
            "supervisor_option",
            "respondent",
            "supervisor",
            "completed_at",
        )
        interfaces = (relay.Node,)

    def resolve_average_score(self, info):
        return float(self.average_score or 0)


class SurveyType(DjangoObjectType):
    responses = graphene.List(ResponseType)
    analytics_summary = graphene.JSONString(description="Hierarchical analytic report")
    trend_data = graphene.JSONString(description="Chart-ready time-series data")

    class Meta:
        model = Survey
        fields = (
            "id",
            "name",
            "slug",
            "unit",
            "start_date",
            "end_date",
            "average_score",
            "share_state",
            "share_uuid",
        )
        interfaces = (relay.Node,)

    def resolve_responses(self, info):
        return (
            self.responses.select_related(
                "question__thematic_area__category",
                "self_option",
                "supervisor_option",
            )
            .prefetch_related("question__options")
            .all()
        )

    def resolve_analytics_summary(self, info):
        return self.hierarchical_report()

    def resolve_trend_data(self, info):
        # Generates chart-ready data (e.g., category-level time-series)
        data = []
        for cat in Category.objects.all():
            data.append({
                "category": cat.name,
                "average": float(cat.average_score(self)),
                "total": float(cat.total_score(self)),
            })
        return data


# ==============================================================================
# QUERIES
# ==============================================================================

class Query(graphene.ObjectType):
    node = relay.Node.Field()

    all_surveys = DjangoFilterConnectionField(SurveyType)
    all_categories = DjangoFilterConnectionField(CategoryType)
    all_units = DjangoFilterConnectionField(OperationalUnitType)

    survey = graphene.Field(SurveyType, id=graphene.ID(required=True))
    analytics_dashboard = graphene.JSONString(
        survey_id=graphene.ID(required=True),
        description="Aggregated dashboard-ready analytics"
    )

    def resolve_survey(self, info, id):
        return (
            Survey.objects.prefetch_related(
                "responses__question__thematic_area__category"
            )
            .select_related("unit")
            .filter(pk=id)
            .first()
        )

    def resolve_analytics_dashboard(self, info, survey_id):
        survey = Survey.objects.filter(id=survey_id).first()
        if not survey:
            raise GraphQLError("Survey not found.")
        data = survey.hierarchical_report()
        # Flattened dashboard metrics for chart visualization
        flat = []
        for category, areas in data.items():
            for area, stats in areas.items():
                flat.append({
                    "category": category,
                    "area": area,
                    "avg": stats["average_score"],
                    "total": stats["total_score"],
                })
        return {"hierarchy": data, "flat": flat}


# ==============================================================================
# MUTATIONS
# ==============================================================================

class SubmitResponse(graphene.Mutation):
    """Submit or update a response atomically and trigger recalculation."""
    class Arguments:
        survey_id = graphene.ID(required=True)
        question_id = graphene.ID(required=True)
        self_option_id = graphene.ID(required=False)
        supervisor_option_id = graphene.ID(required=False)

    ok = graphene.Boolean()
    response = graphene.Field(ResponseType)
    updated_average = graphene.Float()

    @classmethod
    @transaction.atomic
    def mutate(cls, root, info, survey_id, question_id, self_option_id=None, supervisor_option_id=None):
        user = info.context.user
        if not user or not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        survey = Survey.objects.select_for_update().get(pk=survey_id)
        question = Question.objects.get(pk=question_id)

        response, _ = Response.objects.update_or_create(
            survey=survey,
            question=question,
            respondent=user,
            defaults={
                "self_option_id": self_option_id,
                "supervisor_option_id": supervisor_option_id,
                "supervisor": None,
            },
        )

        # Trigger recalculation atomically
        survey.recalc_average()
        survey.save(update_fields=["average_score"])

        return SubmitResponse(ok=True, response=response, updated_average=float(survey.average_score))


class RecalculateSurvey(graphene.Mutation):
    """Force a full recalculation of a survey's analytics (cached)."""
    class Arguments:
        survey_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    survey = graphene.Field(SurveyType)

    @classmethod
    @transaction.atomic
    def mutate(cls, root, info, survey_id):
        survey = Survey.objects.select_for_update().get(pk=survey_id)
        survey.recalc_average()
        survey.save()
        return RecalculateSurvey(ok=True, survey=survey)


class CloneSurvey(graphene.Mutation):
    """Duplicate a survey (structure only or with responses)."""
    class Arguments:
        source_id = graphene.ID(required=True)
        name = graphene.String(required=True)
        include_responses = graphene.Boolean(default_value=False)

    ok = graphene.Boolean()
    new_survey = graphene.Field(SurveyType)

    @classmethod
    @transaction.atomic
    def mutate(cls, root, info, source_id, name, include_responses):
        src = Survey.objects.prefetch_related("responses").get(pk=source_id)
        new_survey = Survey.objects.create(
            unit=src.unit,
            name=name,
            start_date=src.start_date,
            end_date=src.end_date,
        )
        if include_responses:
            for resp in src.responses.all():
                Response.objects.create(
                    survey=new_survey,
                    question=resp.question,
                    self_option=resp.self_option,
                    supervisor_option=resp.supervisor_option,
                    respondent=resp.respondent,
                    supervisor=resp.supervisor,
                )
        new_survey.recalc_average()
        new_survey.save()
        return CloneSurvey(ok=True, new_survey=new_survey)


class Mutation(graphene.ObjectType):
    submit_response = SubmitResponse.Field()
    recalculate_survey = RecalculateSurvey.Field()
    clone_survey = CloneSurvey.Field()


# ==============================================================================
# SCHEMA
# ==============================================================================

schema = graphene.Schema(query=Query, mutation=Mutation)
