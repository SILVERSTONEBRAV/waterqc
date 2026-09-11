# qc/utils/instrument_integration.py
from instruments.models import OnlineMeasurement, Sensor, QualityFlag, TreatmentStage

# Map Water Type -> Sensor Stage
WATER_TYPE_STAGE_MAP = {
    "raw": TreatmentStage.RAW_WATER,
    "treated": TreatmentStage.TREATED,
    "coagulated": TreatmentStage.COAGULATED,
    "clarified": TreatmentStage.CLARIFIED,
}


def import_instrument_readings(water_analysis):
    """
    Populate WaterAnalysis results from latest instrument measurements.
    Handles multiple parameters per water type.
    Only considers readings with quality_flag OK or SUSPECT.
    Supports manual entry if no sensor exists.
    """
    # Import here to avoid circular import
    from qc.models import (
        WaterAnalysis,
        RawWaterResult, TreatedWaterResult,
        CoagulatedWaterResult, ClarifiedWaterResult,
        BaseResultPlaceholder
    )

    # Map Water Type -> Result Model (deferred import)
    WATER_TYPE_RESULT_MODEL = {
        "raw": RawWaterResult,
        "treated": TreatedWaterResult,
        "coagulated": CoagulatedWaterResult,
        "clarified": ClarifiedWaterResult,
    }

    water_type = water_analysis.analysis_time.water_type
    stage = WATER_TYPE_STAGE_MAP.get(water_type)
    ResultModel = WATER_TYPE_RESULT_MODEL.get(water_type)
    if not stage or not ResultModel:
        return

    # Get all active sensors for the treatment plant and stage
    sensors = Sensor.objects.filter(
        treatment_plant=water_analysis.treatment_plant,
        stage=stage,
        is_active=True
    )

    if not sensors.exists():
        # No sensors: create manual placeholders for all parameters of this type
        if water_type == "raw":
            from t.models import RawWaterLimit as LimitModel
        elif water_type == "treated":
            from t.models import TreatedWaterLimit as LimitModel
        elif water_type == "coagulated":
            from t.models import CoagulatedWaterLimit as LimitModel
        elif water_type == "clarified":
            from t.models import ClarifiedWaterLimit as LimitModel
        else:
            return

        for limit in LimitModel.objects.all():
            BaseResultPlaceholder.create_for_limit(limit, water_analysis)
        return

    for sensor in sensors:
        # Get the latest measurement that is valid
        measurement = (
            OnlineMeasurement.objects.filter(sensor=sensor)
            .exclude(quality_flag=QualityFlag.INVALID)
            .order_by('-measured_at')
            .first()
        )
        if not measurement:
            # No reading yet: create placeholder for manual entry
            BaseResultPlaceholder.create_for_limit(sensor.parameter, water_analysis)
            continue

        # Create or update the WaterAnalysis result for this parameter
        result, created = ResultModel.objects.update_or_create(
            analysis=water_analysis,
            parameter=sensor.parameter,
            defaults={"value": measurement.value}
        )

        # Trigger nonconformity detection & save
        result.save()
