# qc/services/analysis_generator.py

from __future__ import annotations

import logging

from datetime import datetime, timedelta
from typing import Optional

from asgiref.sync import async_to_sync

from channels.layers import get_channel_layer

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from qc.models import (
    SamplingTime,
    WaterAnalysis,
    WaterAnalysisLog,
)

from qc.services.result_generator import (
    AnalysisResultGenerator,
)

from sc.models import Shift


logger = logging.getLogger(__name__)


class AnalysisGenerator:

    CACHE_PREFIX = "qc-analysis-generator"

    CACHE_LOCK_SECONDS = 300

    SAMPLE_WINDOW_MINUTES = 2

    CURRENT_ANALYSIS_DISPLAY_MINUTES = 30


    # ======================================================
    # PUBLIC ENTRY POINT
    # ======================================================

    @classmethod
    def generate_due_analyses(
        cls,
        target_datetime=None,
        force=False,
        backfill_minutes=5,
        plant_ids=None,
    ):

        now = cls._normalize_datetime(
            target_datetime or timezone.now()
        )

        stats = cls._result()


        cursor = (
            now -
            timedelta(
                minutes=backfill_minutes
            )
        ).replace(
            second=0,
            microsecond=0,
        )


        logger.info(
            "[QC] Generation started %s",
            now,
        )


        while cursor <= now:

            result = cls.generate_for_time(
                current_datetime=cursor,
                force=force,
                plant_ids=plant_ids,
            )


            cls._merge(
                stats,
                result,
            )


            cursor += timedelta(
                minutes=1
            )


        logger.info(
            "[QC] Generation completed %s",
            stats,
        )


        return stats



    @classmethod
    def generate_for_time(
        cls,
        current_datetime,
        force=False,
        plant_ids=None,
    ):

        current_datetime = cls._normalize_datetime(
            current_datetime
        )


        samples = cls._get_due_samples(
            current_datetime,
            plant_ids,
        )


        stats = cls._result()


        logger.info(
            "[QC] Due samples=%s",
            samples.count(),
        )


        for sample in samples:

            result = cls._generate_sample(
                sample,
                current_datetime,
                force,
            )


            cls._merge(
                stats,
                result,
            )


        return stats



    # ======================================================
    # SINGLE SAMPLE
    # ======================================================

    @classmethod
    def _generate_sample(
        cls,
        sample,
        current_datetime,
        force=False,
    ):

        stats = cls._result()


        schedule = sample.schedule

        plant = schedule.treatment_plant


        lock_key = (
            f"{cls.CACHE_PREFIX}:"
            f"{plant.pk}:"
            f"{sample.pk}:"
            f"{current_datetime.date()}"
        )


        if not cache.add(
            lock_key,
            True,
            cls.CACHE_LOCK_SECONDS,
        ):

            stats["skipped"] = True

            return stats



        try:

            sample_datetime = cls._sample_datetime(
                current_datetime.date(),
                sample.time,
            )


            shift = Shift.get_shift_for_time(
                sample_datetime,
                treatment_plant=plant,
            )


            if not force and cls._exists(
                plant.pk,
                current_datetime.date(),
                sample.pk,
            ):

                stats["existing"] += 1

                return stats



            with transaction.atomic():

                analysis = WaterAnalysis.objects.create(
                    treatment_plant=plant,
                    analysis_date=current_datetime.date(),
                    analysis_time=sample,
                    shift=shift,
                )


                cls._create_log(
                    analysis,
                    sample,
                )


            stats["created"] += 1



            cls._generate_results(
                analysis,
                stats,
            )


            cls._broadcast(
                analysis,
                plant,
                sample,
            )


            logger.info(
                "[QC] Created analysis=%s plant=%s shift=%s",
                analysis.pk,
                plant.name,
                shift.name if shift else None,
            )


            return stats



        except IntegrityError:

            stats["existing"] += 1

            logger.warning(
                "[QC] Duplicate prevented plant=%s sample=%s",
                plant.pk,
                sample.pk,
            )

            return stats



        except Exception:

            stats["errors"] += 1

            logger.exception(
                "[QC] Generation failed sample=%s",
                sample.pk,
            )

            return stats


        finally:

            cache.delete(
                lock_key
            )
    # ======================================================
    # RESULT GENERATION
    # ======================================================

    @classmethod
    def _generate_results(
        cls,
        analysis,
        stats,
    ):

        try:

            result = (
                AnalysisResultGenerator
                .generate_for_analysis(
                    analysis,
                    force=False,
                )
            )


            stats["errors"] += getattr(
                result,
                "errors",
                0,
            )


            logger.info(
                "[QC] Results generated analysis=%s created=%s",
                analysis.pk,
                getattr(
                    result,
                    "created",
                    0,
                ),
            )


        except Exception:

            stats["errors"] += 1

            logger.exception(
                "[QC] Result generation failed analysis=%s",
                analysis.pk,
            )



    # ======================================================
    # WEBSOCKET BROADCAST
    # ======================================================

    @classmethod
    def _broadcast(
        cls,
        analysis,
        plant,
        sample,
    ):

        try:

            channel_layer = get_channel_layer()


            if channel_layer is None:
                return


            payload = {

                "analysis_id":
                    analysis.pk,

                "plant_id":
                    plant.pk,

                "water_type":
                    sample.schedule.get_water_type_display(),

                "timestamp":
                    timezone.now().isoformat(),

            }


            async_to_sync(
                channel_layer.group_send
            )(
                f"qc-plant-{plant.pk}",
                {
                    "type":
                        "analysis_created",
                    **payload,
                },
            )


            async_to_sync(
                channel_layer.group_send
            )(
                f"qc-plant-{plant.pk}",
                {
                    "type":
                        "qc_results_updated",
                    **payload,
                },
            )


            logger.info(
                "[QC WS] Broadcast analysis=%s plant=%s",
                analysis.pk,
                plant.pk,
            )


        except Exception:

            logger.exception(
                "[QC WS] Broadcast failed analysis=%s",
                analysis.pk,
            )



    # ======================================================
    # AUDIT LOG
    # ======================================================

    @classmethod
    def _create_log(
        cls,
        analysis,
        sample,
    ):

        exists = (
            WaterAnalysisLog.objects
            .filter(
                analysis=analysis,
                action="auto_generated",
            )
            .exists()
        )


        if exists:
            return



        WaterAnalysisLog.objects.create(
            analysis=analysis,
            action="auto_generated",
            remarks=(
                "Automatically generated "
                f"{analysis.analysis_date} "
                f"{sample.time.strftime('%H:%M')} "
                f"{sample.schedule.get_water_type_display()}"
            ),
            auto_generated=True,
        )



    # ======================================================
    # SAMPLE QUERY
    # ======================================================

    @classmethod
    def _get_due_samples(
        cls,
        current_datetime,
        plant_ids=None,
    ):

        start = (
            current_datetime -
            timedelta(
                minutes=cls.SAMPLE_WINDOW_MINUTES
            )
        ).time()


        end = (
            current_datetime +
            timedelta(
                minutes=cls.SAMPLE_WINDOW_MINUTES
            )
        ).time()



        queryset = (
            SamplingTime.objects
            .filter(
                schedule__enabled=True,
            )
            .select_related(
                "schedule",
                "schedule__treatment_plant",
            )
        )


        if plant_ids:

            queryset = queryset.filter(
                schedule__treatment_plant_id__in=plant_ids
            )



        if start <= end:

            return queryset.filter(
                time__range=(
                    start,
                    end,
                )
            )


        return (
            queryset.filter(
                time__gte=start
            )
            |
            queryset.filter(
                time__lte=end
            )
        )



    # ======================================================
    # DUPLICATE PROTECTION
    # ======================================================

    @staticmethod
    def _exists(
        plant_id,
        analysis_date,
        sampling_time_id,
    ):

        return (
            WaterAnalysis.objects
            .filter(
                treatment_plant_id=plant_id,
                analysis_date=analysis_date,
                analysis_time_id=sampling_time_id,
            )
            .exists()
        )



    # ======================================================
    # CURRENT ANALYSIS
    # ======================================================

    @classmethod
    def get_current_analysis(
        cls,
        *,
        treatment_plant,
        now=None,
    ):

        now = cls._normalize_datetime(
            now or timezone.now()
        )


        analyses = list(
            WaterAnalysis.objects
            .filter(
                treatment_plant=treatment_plant,
                analysis_date=now.date(),
            )
            .select_related(
                "analysis_time",
                "analysis_time__schedule",
                "shift",
            )
            .order_by(
                "analysis_time__time"
            )
        )


        if not analyses:
            return None



        current_minutes = (
            now.hour * 60
            +
            now.minute
        )



        closest = None

        smallest_difference = None



        for analysis in analyses:

            sample_time = (
                analysis
                .analysis_time
                .time
            )


            sample_minutes = (
                sample_time.hour * 60
                +
                sample_time.minute
            )


            difference = (
                current_minutes
                -
                sample_minutes
            )


            if difference < 0:
                continue



            if (
                smallest_difference is None
                or difference < smallest_difference
            ):

                smallest_difference = difference

                closest = analysis



        if closest:

            return closest



        return analyses[-1]

    @classmethod
    def get_header_context(
            cls,
            user,
            now=None,
    ):

        now = cls._normalize_datetime(
            now or timezone.now()
        )

        plant = getattr(
            user,
            "assigned_treatment_plant",
            None,
        )

        lab = getattr(
            user,
            "assigned_lab",
            None,
        )

        current_analysis = None
        current_shift = None
        shift_supervisors = []

        if plant:

            current_analysis = (
                cls.get_current_analysis(
                    treatment_plant=plant,
                    now=now,
                )
            )

            if current_analysis:

                current_shift = (
                    current_analysis.shift
                )

                if current_shift:

                    from sc.models import (
                        ShiftSupervisor,
                    )

                    user_section = getattr(
                        user,
                        "section",
                        None,
                    )

                    supervisor_query = (
                        ShiftSupervisor.objects
                        .filter(
                            treatment_plant=plant,
                            is_active=True,
                        )
                        .select_related(
                            "user",
                        )
                    )

                    if user_section:
                        supervisor_query = (
                            supervisor_query
                            .filter(
                                user__section=user_section
                            )
                        )

                    shift_supervisors = list(
                        supervisor_query
                    )

        return {

            "assigned_plant":
                plant,

            "assigned_lab":
                lab,

            # ALWAYS derived from current analysis
            "current_shift":
                current_shift,

            "current_analysis":
                current_analysis,

            "shift_supervisors":
                shift_supervisors,

            "current_time":
                now,

        }


    # ======================================================
    # DATETIME HELPERS
    # ======================================================

    @staticmethod
    def _sample_datetime(
        analysis_date,
        sample_time,
    ):

        value = datetime.combine(
            analysis_date,
            sample_time,
        )


        return timezone.make_aware(
            value
        )



    @staticmethod
    def _normalize_datetime(
        value,
    ):

        if timezone.is_naive(value):

            value = timezone.make_aware(
                value
            )


        return timezone.localtime(
            value
        )



    # ======================================================
    # STATS
    # ======================================================

    @staticmethod
    def _merge(
        target,
        source,
    ):

        target["created"] += (
            source["created"]
        )

        target["existing"] += (
            source["existing"]
        )

        target["errors"] += (
            source["errors"]
        )


        if source.get("skipped"):

            target["skipped"] = True



    @staticmethod
    def _result(
        created=0,
        existing=0,
        errors=0,
        skipped=False,
    ):

        return {

            "created":
                created,

            "existing":
                existing,

            "errors":
                errors,

            "skipped":
                skipped,

            "generated_at":
                timezone.now(),

        }