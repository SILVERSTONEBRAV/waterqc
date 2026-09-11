from __future__ import annotations

import logging

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Type

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from qc.models import (
    SamplingSchedule,
    WaterAnalysis,
    WaterAnalysisLog,
    RawWaterResult,
    TreatedWaterResult,
    CoagulatedWaterResult,
    ClarifiedWaterResult,
)

from t.models import (
    RawWaterLimit,
    TreatedWaterLimit,
    CoagulatedWaterLimit,
    ClarifiedWaterLimit,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GenerationResult:
    created: int = 0
    existing: int = 0
    errors: int = 0

    def __getitem__(self, key):
        return getattr(self, key)

    def __iadd__(self, other: "GenerationResult"):
        self.created += other.created
        self.existing += other.existing
        self.errors += other.errors
        return self


class AnalysisResultGenerator:

    BATCH_SIZE = 1000

    LIMIT_MODEL_MAP: Dict[str, Type] = {
        SamplingSchedule.RAW: RawWaterLimit,
        SamplingSchedule.TREATED: TreatedWaterLimit,
        SamplingSchedule.COAGULATED: CoagulatedWaterLimit,
        SamplingSchedule.CLARIFIED: ClarifiedWaterLimit,
    }

    RESULT_MODEL_MAP: Dict[str, Type] = {
        SamplingSchedule.RAW: RawWaterResult,
        SamplingSchedule.TREATED: TreatedWaterResult,
        SamplingSchedule.COAGULATED: CoagulatedWaterResult,
        SamplingSchedule.CLARIFIED: ClarifiedWaterResult,
    }

    @classmethod
    def generate_for_analysis(
        cls,
        analysis: WaterAnalysis,
        *,
        force: bool = False,
    ) -> GenerationResult:

        water_type = analysis.water_type

        ResultModel = cls.RESULT_MODEL_MAP.get(water_type)
        LimitModel = cls.LIMIT_MODEL_MAP.get(water_type)

        if ResultModel is None or LimitModel is None:
            logger.error(
                "Unsupported water type '%s' for analysis %s",
                water_type,
                analysis.pk,
            )
            return GenerationResult(errors=1)

        try:

            with transaction.atomic():

                limits = list(
                    LimitModel.objects.filter(
                        treatment_plant=analysis.treatment_plant,
                    )
                    .select_related("parameter")
                    .order_by("parameter__name")
                )

                if not limits:
                    logger.warning(
                        "No limits configured for plant=%s water=%s",
                        analysis.treatment_plant_id,
                        water_type,
                    )
                    return GenerationResult()

                phases = cls._get_phases(analysis)

                existing = cls._existing_keys(
                    ResultModel,
                    analysis,
                )

                rows = cls._build_rows(
                    ResultModel=ResultModel,
                    analysis=analysis,
                    limits=limits,
                    phases=phases,
                    existing=existing,
                    force=force,
                )

                before = len(existing)

                if rows:
                    ResultModel.objects.bulk_create(
                        rows,
                        batch_size=cls.BATCH_SIZE,
                    )

                after = (
                    ResultModel.objects
                    .filter(
                        analysis=analysis,
                    )
                    .count()
                )

                created = max(after - before, 0)

                WaterAnalysisLog.objects.get_or_create(
                    analysis=analysis,
                    action="results_generated",
                    defaults={
                        "remarks": (
                            f"{created} parameter results generated automatically."
                        ),
                        "auto_generated": True,
                    },
                )

                transaction.on_commit(
                    lambda: cls._broadcast_results_created(
                        analysis
                    )
                )

                logger.info(
                    "Generated results analysis=%s created=%s existing=%s",
                    analysis.pk,
                    created,
                    before,
                )

                return GenerationResult(
                    created=created,
                    existing=before,
                    errors=0,
                )

        except Exception:
            logger.exception(
                "Failed generating results for analysis=%s",
                analysis.pk,
            )
            return GenerationResult(errors=1)

    @staticmethod
    def _get_phases(
        analysis: WaterAnalysis,
    ) -> List:

        if analysis.water_type == SamplingSchedule.RAW:
            return []

        return list(
            analysis.treatment_plant.phases.order_by("pk")
        )

    @staticmethod
    def _existing_keys(
        ResultModel,
        analysis,
    ) -> Set[Tuple[int, int | None]]:

        return set(
            ResultModel.objects.filter(
                analysis=analysis,
            ).values_list(
                "parameter_id",
                "phase_id",
            )
        )

    @classmethod
    def _build_rows(
        cls,
        *,
        ResultModel,
        analysis,
        limits,
        phases,
        existing,
        force,
    ):
        rows = []
        if phases:

            for limit in limits:

                for phase in phases:

                    key = (
                        limit.pk,
                        phase.pk,
                    )

                    if not force and key in existing:
                        continue

                    rows.append(
                        ResultModel(
                            analysis=analysis,
                            parameter=limit,
                            phase=phase,
                            value=None,
                        )
                    )

        else:

            for limit in limits:

                key = (
                    limit.pk,
                    None,
                )

                if not force and key in existing:
                    continue

                rows.append(
                    ResultModel(
                        analysis=analysis,
                        parameter=limit,
                        value=None,
                    )
                )

        return rows

    @staticmethod
    def _broadcast_results_created(
            analysis: WaterAnalysis,
    ):

        try:

            channel_layer = get_channel_layer()

            if channel_layer is None:
                return

            async_to_sync(
                channel_layer.group_send
            )(
                f"qc-plant-{analysis.treatment_plant_id}",
                {
                    "type": "qc.results.updated",
                    "analysis_id": analysis.pk,
                    "plant_id": analysis.treatment_plant_id,
                    "water_type": analysis.water_type,
                    "timestamp": timezone.now().isoformat(),
                },
            )

        except Exception:

            logger.exception(
                "Failed websocket notification for analysis=%s",
                analysis.pk,
            )

    @classmethod
    def generate_for_queryset(
            cls,
            queryset: QuerySet[WaterAnalysis],
            *,
            force: bool = False,
    ) -> GenerationResult:

        queryset = (
            queryset
            .select_related(
                "analysis_time",
                "analysis_time__schedule",
                "treatment_plant",
            )
            .order_by(
                "analysis_date",
                "analysis_time__time",
            )
        )

        summary = GenerationResult()

        for analysis in queryset.iterator(
                chunk_size=cls.BATCH_SIZE,
        ):
            summary += cls.generate_for_analysis(
                analysis,
                force=force,
            )

        logger.info(
            "Batch result generation complete created=%s existing=%s errors=%s",
            summary.created,
            summary.existing,
            summary.errors,
        )

        return summary