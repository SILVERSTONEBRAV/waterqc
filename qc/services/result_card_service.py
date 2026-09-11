from __future__ import annotations

import logging

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Type

from django.apps import apps
from django.db.models import QuerySet
from django.utils import timezone

from qc.models import (
    SamplingSchedule,
    SamplingTime,
    WaterAnalysis,
)


logger = logging.getLogger(__name__)


WATER_CONFIG = {
    SamplingSchedule.RAW: {
        "model": "RawWaterResult",
        "title": "RAW WATER",
        "order": 1,
    },
    SamplingSchedule.COAGULATED: {
        "model": "CoagulatedWaterResult",
        "title": "COAGULATED WATER",
        "order": 2,
    },
    SamplingSchedule.CLARIFIED: {
        "model": "ClarifiedWaterResult",
        "title": "CLARIFIED WATER",
        "order": 3,
    },
    SamplingSchedule.TREATED: {
        "model": "TreatedWaterResult",
        "title": "TREATED WATER",
        "order": 4,
    },
}


@dataclass(slots=True)
class ResultCell:

    result: Any

    parameter: str

    unit: str

    value: Optional[Decimal]

    minimum: Optional[Decimal]

    maximum: Optional[Decimal]

    entered: bool

    abnormal: bool

    display_value: str

    display_limit: str


@dataclass(slots=True)
class ResultRow:

    name: str

    results: Dict[str, ResultCell] = field(
        default_factory=dict
    )


@dataclass(slots=True)
class ResultGroup:

    title: str

    water_type: str

    rows: List[ResultRow] = field(
        default_factory=list
    )

    parameters: List[dict] = field(
        default_factory=list
    )


@dataclass(slots=True)
class AnalysisCard:

    sampling_time: SamplingTime

    time_label: str

    groups: List[ResultGroup]


class ResultCardService:

    _result_cache: Dict[str, Type] = {}

    @classmethod
    def get_result_model(
        cls,
        water_type: str,
    ) -> Optional[Type]:

        if water_type in cls._result_cache:
            return cls._result_cache[water_type]

        config = WATER_CONFIG.get(
            water_type
        )

        if not config:
            return None

        model = apps.get_model(
            "qc",
            config["model"],
        )

        if model:
            cls._result_cache[water_type] = model

        return model


    @classmethod
    def get_active_analyses(
        cls,
        *,
        treatment_plant,
        selected_date=None,
    ) -> QuerySet:

        analysis_date = (
            selected_date
            or timezone.localdate()
        )

        return (
            WaterAnalysis.objects
            .filter(
                treatment_plant=treatment_plant,
                analysis_date=analysis_date,
            )
            .select_related(
                "analysis_time",
                "analysis_time__schedule",
                "shift",
                "treatment_plant",
            )
            .order_by(
                "-analysis_time__time",
                "analysis_time__schedule__water_type",
            )
        )


    @classmethod
    def preload_results(
        cls,
        analyses: Iterable[WaterAnalysis],
    ) -> Dict[int, list]:

        result_map = defaultdict(list)

        grouped = defaultdict(list)

        for analysis in analyses:

            model = cls.get_result_model(
                analysis.water_type
            )

            if model:
                grouped[model].append(
                    analysis.id
                )


        for model, analysis_ids in grouped.items():

            results = (
                model.objects
                .filter(
                    analysis_id__in=analysis_ids
                )
                .select_related(
                    "analysis",
                    "parameter",
                    "parameter__parameter",
                    "phase",
                )
                .order_by(
                    "phase__name",
                    "parameter__parameter__name",
                )
            )

            for result in results:

                result_map[
                    result.analysis_id
                ].append(
                    result
                )

        return result_map
    @classmethod
    def build_time_card(
        cls,
        analyses: List[WaterAnalysis],
        result_map: Dict[int, list],
        plant_has_phases: bool,
    ) -> Optional[AnalysisCard]:

        if not analyses:
            return None

        sampling_time = analyses[0].analysis_time

        groups = []

        for analysis in analyses:

            group = cls.build_group(
                analysis=analysis,
                results=result_map.get(
                    analysis.id,
                    [],
                ),
                plant_has_phases=plant_has_phases,
            )

            if group:
                groups.append(group)

        groups.sort(
            key=lambda group:
            WATER_CONFIG.get(
                group.water_type,
                {},
            ).get(
                "order",
                99,
            )
        )

        if not groups:
            return None

        return AnalysisCard(
            sampling_time=sampling_time,
            time_label=sampling_time.time.strftime(
                "%H:%M"
            ),
            groups=groups,
        )


    @classmethod
    def build_group(
        cls,
        *,
        analysis: WaterAnalysis,
        results: List[Any],
        plant_has_phases: bool,
    ) -> Optional[ResultGroup]:

        title = cls.water_title(
            analysis.water_type
        )

        rows = defaultdict(
            lambda: ResultRow(
                name=""
            )
        )

        for result in results:

            parameter = cls.resolve_parameter(
                result
            )

            if not parameter:
                continue

            row_name = cls.resolve_row_name(
                analysis,
                result,
                plant_has_phases,
            )

            row = rows[row_name]

            row.name = row_name

            row.results[
                parameter.name
            ] = cls.make_cell(
                result
            )

        if not rows:

            rows[title] = ResultRow(
                name=title
            )

        return ResultGroup(
            title=title,
            water_type=analysis.water_type,
            rows=list(
                rows.values()
            ),
            parameters=cls.extract_parameters(
                results
            ),
        )


    @staticmethod
    def water_title(
        water_type: str,
    ) -> str:

        return (
            WATER_CONFIG
            .get(
                water_type,
                {},
            )
            .get(
                "title",
                str(water_type).upper(),
            )
        )


    @staticmethod
    def resolve_parameter(
        result,
    ):

        parameter_limit = getattr(
            result,
            "parameter",
            None,
        )

        if not parameter_limit:
            return None

        return getattr(
            parameter_limit,
            "parameter",
            None,
        )


    @classmethod
    def resolve_row_name(
        cls,
        analysis,
        result,
        plant_has_phases: bool,
    ):

        if (
            plant_has_phases
            and result.phase_id
            and result.phase
        ):
            return result.phase.name

        return cls.water_title(
            analysis.water_type
        )


    @staticmethod
    def extract_parameters(
        results: List[Any],
    ) -> List[dict]:

        parameters = {}

        for result in results:

            parameter = ResultCardService.resolve_parameter(
                result
            )

            if not parameter:
                continue

            parameters[
                parameter.pk
            ] = {
                "id": parameter.pk,
                "name": parameter.name,
                "unit": getattr(
                    parameter,
                    "unit",
                    "",
                ),
                "order": getattr(
                    parameter,
                    "display_order",
                    0,
                ),
            }

        return sorted(
            parameters.values(),
            key=lambda item: item["order"],
        )


    @classmethod
    def make_cell(
        cls,
        result,
    ) -> ResultCell:

        parameter_limit = getattr(
            result,
            "parameter",
            None,
        )

        parameter = cls.resolve_parameter(
            result
        )

        value = getattr(
            result,
            "value",
            None,
        )

        minimum = getattr(
            parameter_limit,
            "min_value",
            None,
        )

        maximum = getattr(
            parameter_limit,
            "max_value",
            None,
        )

        abnormal = cls.is_abnormal(
            result=result,
            value=value,
            minimum=minimum,
            maximum=maximum,
        )

        return ResultCell(
            result=result,
            parameter=(
                parameter.name
                if parameter
                else ""
            ),
            unit=(
                getattr(
                    parameter,
                    "unit",
                    "",
                )
                if parameter
                else ""
            ),
            value=value,
            minimum=minimum,
            maximum=maximum,
            entered=value is not None,
            abnormal=abnormal,
            display_value=cls.display_value(
                value
            ),
            display_limit=cls.limit_text(
                minimum,
                maximum,
            ),
        )
    @staticmethod
    def is_abnormal(
        *,
        result,
        value,
        minimum,
        maximum,
    ) -> bool:

        stored_status = getattr(
            result,
            "is_abnormal",
            None,
        )

        if stored_status is not None:
            return stored_status

        exceeds_limit = getattr(
            result,
            "exceeds_limit",
            None,
        )

        if exceeds_limit is not None:
            return exceeds_limit

        if value is None:
            return False

        if minimum is not None and value < minimum:
            return True

        if maximum is not None and value > maximum:
            return True

        return False


    @staticmethod
    def display_value(
        value,
    ) -> str:

        if value is None:
            return "—"

        return str(value)


    @staticmethod
    def limit_text(
        minimum,
        maximum,
    ) -> str:

        if (
            minimum is None
            and maximum is None
        ):
            return ""

        if minimum is None:
            return f"≤ {maximum}"

        if maximum is None:
            return f"≥ {minimum}"

        return f"{minimum} – {maximum}"

    @classmethod
    def get_context(
            cls,
            *,
            treatment_plant,
            selected_date=None,
    ):

        generated_at = timezone.localtime()

        # --------------------------------------------------
        # No plant assigned
        # --------------------------------------------------

        if not treatment_plant:
            return {
                "cards": [],
                "plant": None,
                "generated_at": generated_at,
                "current_only": True,
            }

        # --------------------------------------------------
        # Load today's analyses
        # --------------------------------------------------

        analyses = list(
            cls.get_active_analyses(
                treatment_plant=treatment_plant,
                selected_date=selected_date,
            )
        )

        # --------------------------------------------------
        # No scheduled analyses
        # --------------------------------------------------

        if not analyses:
            return {
                "cards": [],
                "plant": treatment_plant,
                "generated_at": generated_at,
                "current_only": True,
            }

        # --------------------------------------------------
        # Load all results efficiently
        # --------------------------------------------------

        result_map = cls.preload_results(
            analyses
        )

        # --------------------------------------------------
        # Determine plant phase support
        # --------------------------------------------------

        plant_has_phases = (
            treatment_plant
            .phases
            .exists()
        )

        # ==================================================
        # CURRENT SAMPLING CYCLE ONLY
        # ==================================================

        latest_sampling_time = max(
            analysis.analysis_time.time
            for analysis in analyses
        )

        current_analyses = [
            analysis
            for analysis in analyses
            if analysis.analysis_time.time
               == latest_sampling_time
        ]

        # --------------------------------------------------
        # Build single dashboard card
        # --------------------------------------------------

        card = cls.build_time_card(
            analyses=current_analyses,
            result_map=result_map,
            plant_has_phases=plant_has_phases,
        )

        cards = []

        if card:
            cards.append(card)

        # --------------------------------------------------
        # Return dashboard context
        # --------------------------------------------------

        return {
            "cards": cards,
            "plant": treatment_plant,
            "generated_at": generated_at,
            "current_only": True,
        }

    @classmethod
    def for_request(
        cls,
        request,
    ):

        plant = getattr(
            request.user,
            "assigned_treatment_plant",
            None,
        )

        return cls.get_context(
            treatment_plant=plant,
        )