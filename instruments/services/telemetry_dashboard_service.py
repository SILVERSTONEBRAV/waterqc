from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from django.db.models import Max, Q
from django.utils import timezone

from instruments.models import (
    Instrument,
    InstrumentStatus,
    OnlineMeasurement,
    QualityFlag,
    Sensor,
    TreatmentStage,
)
from parameters.models import PhysicochemicalParameter
from t.models import TreatmentPlant, TreatmentPlantPhase

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SensorCell:
    sensor_id: Optional[str] = None
    sensor_name: str = ""
    instrument_name: str = ""
    instrument_serial: str = ""
    instrument_protocol: str = ""
    instrument_status: str = "offline"
    phase_name: str = ""
    parameter_id: Optional[str] = None
    parameter_name: str = ""
    unit: str = ""
    value: Optional[Decimal] = None
    formatted_value: str = "—"
    quality_flag: str = ""
    status: str = "no_sensor"  # "normal", "warning", "danger", "stale", "offline", "no_sensor"
    status_label: str = "Unmonitored"
    measured_at: Optional[datetime] = None
    time_ago: str = ""
    min_detectable: Optional[Decimal] = None
    max_detectable: Optional[Decimal] = None
    is_out_of_bounds: bool = False
    drift_score: float = 0.0
    anomaly_score: float = 0.0
    signal_strength: Optional[int] = None
    redundant_count: int = 0
    is_primary: bool = True


@dataclass(slots=True)
class TelemetryRow:
    phase_id: Optional[int]
    phase_name: str
    cells: Dict[str, SensorCell] = field(default_factory=dict)


@dataclass(slots=True)
class TelemetryStageGroup:
    stage_key: str
    stage_title: str
    order: int
    parameters: List[PhysicochemicalParameter] = field(default_factory=list)
    rows: List[TelemetryRow] = field(default_factory=list)
    total_sensors: int = 0
    online_sensors: int = 0
    alert_sensors: int = 0


@dataclass(slots=True)
class DashboardKPIs:
    total_instruments: int = 0
    online_instruments: int = 0
    degraded_instruments: int = 0
    offline_instruments: int = 0
    total_sensors: int = 0
    active_sensors: int = 0
    normal_sensors: int = 0
    warning_sensors: int = 0
    danger_sensors: int = 0
    stale_sensors: int = 0
    overall_health_pct: int = 0
    latest_reading_time: Optional[datetime] = None
    latest_reading_ago: str = "Never"


class TelemetryDashboardService:
    """
    High-performance telemetry aggregation service for the treatment plant scoped
    Instruments Dashboard. Generates read-only matrix representations of live sensor feeds.
    """

    STAGE_TITLES: Dict[str, str] = {
        TreatmentStage.RAW_WATER: "RAW WATER",
        TreatmentStage.COAGULATED: "COAGULATED WATER",
        TreatmentStage.CLARIFIED: "CLARIFIED WATER",
        TreatmentStage.FILTERED: "FILTERED WATER",
        TreatmentStage.TREATED: "TREATED WATER",
    }

    STAGE_ORDER: Dict[str, int] = {
        TreatmentStage.RAW_WATER: 1,
        TreatmentStage.COAGULATED: 2,
        TreatmentStage.CLARIFIED: 3,
        TreatmentStage.FILTERED: 4,
        TreatmentStage.TREATED: 5,
    }

    def __init__(self, plant: Optional[TreatmentPlant] = None):
        self.plant = plant

    @staticmethod
    def format_time_ago(dt: Optional[datetime]) -> str:
        if not dt:
            return "No data"
        now = timezone.now()
        seconds = max(0, int((now - dt).total_seconds()))
        if seconds < 15:
            return "just now"
        if seconds < 60:
            return f"{seconds}s ago"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        return f"{days}d ago"

    def get_kpis(self) -> DashboardKPIs:
        kpi = DashboardKPIs()
        if not self.plant:
            return kpi

        instruments = Instrument.objects.filter(treatment_plant=self.plant, is_active=True)
        kpi.total_instruments = instruments.count()
        kpi.online_instruments = instruments.filter(status=InstrumentStatus.ONLINE).count()
        kpi.degraded_instruments = instruments.filter(status=InstrumentStatus.DEGRADED).count()
        kpi.offline_instruments = instruments.filter(
            status__in=[InstrumentStatus.OFFLINE, InstrumentStatus.FAULT, InstrumentStatus.MAINTENANCE]
        ).count()

        sensors = Sensor.objects.filter(treatment_plant=self.plant, is_active=True)
        kpi.total_sensors = sensors.count()
        kpi.active_sensors = sensors.filter(instrument__is_active=True).count()

        latest_m_subquery = (
            OnlineMeasurement.objects.filter(treatment_plant=self.plant)
            .values("sensor_id")
            .annotate(latest_id=Max("id"))
            .values_list("latest_id", flat=True)
        )

        latest_measurements = list(
            OnlineMeasurement.objects.filter(id__in=latest_m_subquery)
            .select_related("sensor", "sensor__instrument")
        )

        now = timezone.now()
        for m in latest_measurements:
            if not kpi.latest_reading_time or m.measured_at > kpi.latest_reading_time:
                kpi.latest_reading_time = m.measured_at

            age_sec = (now - m.measured_at).total_seconds()
            expected_interval = m.sensor.instrument.expected_heartbeat_sec * 3 if m.sensor and m.sensor.instrument else 300
            is_stale = age_sec > expected_interval or age_sec > 900

            if is_stale or m.sensor.instrument.status in [InstrumentStatus.OFFLINE, InstrumentStatus.FAULT]:
                kpi.stale_sensors += 1
            elif (
                m.quality_flag == QualityFlag.INVALID
                or (m.sensor.min_detectable is not None and m.value < m.sensor.min_detectable)
                or (m.sensor.max_detectable is not None and m.value > m.sensor.max_detectable)
            ):
                kpi.danger_sensors += 1
            elif m.quality_flag in [QualityFlag.SUSPECT, QualityFlag.CALIBRATION] or m.anomaly_score > 0.8:
                kpi.warning_sensors += 1
            else:
                kpi.normal_sensors += 1

        if kpi.latest_reading_time:
            kpi.latest_reading_ago = self.format_time_ago(kpi.latest_reading_time)

        if kpi.total_sensors > 0:
            kpi.overall_health_pct = int(round((kpi.normal_sensors / kpi.total_sensors) * 100))
        elif kpi.total_instruments > 0:
            kpi.overall_health_pct = int(round((kpi.online_instruments / kpi.total_instruments) * 100))
        else:
            kpi.overall_health_pct = 100

        return kpi

    def build_telemetry_matrix(self) -> List[TelemetryStageGroup]:
        """
        Builds the Stage -> Phase x Parameter telemetry matrix for the current plant.
        """
        if not self.plant:
            return []

        phases = list(
            TreatmentPlantPhase.objects.filter(treatment_plant=self.plant).order_by("name")
        )

        all_sensors = list(
            Sensor.objects.filter(treatment_plant=self.plant, is_active=True)
            .select_related("instrument", "phase", "parameter")
            .order_by("-is_primary", "name")
        )

        latest_m_subquery = (
            OnlineMeasurement.objects.filter(treatment_plant=self.plant)
            .values("sensor_id")
            .annotate(latest_id=Max("id"))
            .values_list("latest_id", flat=True)
        )

        latest_measurements: Dict[str, OnlineMeasurement] = {
            str(m.sensor_id): m
            for m in OnlineMeasurement.objects.filter(id__in=latest_m_subquery)
        }

        # Index sensors by: (stage, phase_id, parameter_id)
        sensors_by_slot: Dict[tuple, List[Sensor]] = {}
        stage_parameters: Dict[str, Set[PhysicochemicalParameter]] = {
            stage: set() for stage, _ in TreatmentStage.choices
        }

        for sensor in all_sensors:
            p_id = sensor.phase_id
            stage_parameters[sensor.stage].add(sensor.parameter)
            slot_key = (sensor.stage, p_id, str(sensor.parameter.uuid))
            sensors_by_slot.setdefault(slot_key, []).append(sensor)

        stage_groups: List[TelemetryStageGroup] = []
        now = timezone.now()

        for stage_key, stage_label in TreatmentStage.choices:
            distinct_params = sorted(
                list(stage_parameters.get(stage_key, set())),
                key=lambda p: p.name.lower(),
            )

            # If no sensors and no params configured in this stage, skip to keep dashboard tidy
            stage_sensors = [s for s in all_sensors if s.stage == stage_key]
            if not stage_sensors and not distinct_params:
                continue

            stage_group = TelemetryStageGroup(
                stage_key=stage_key,
                stage_title=self.STAGE_TITLES.get(stage_key, stage_label.upper()),
                order=self.STAGE_ORDER.get(stage_key, 99),
                parameters=distinct_params,
                rows=[],
                total_sensors=len(stage_sensors),
            )

            # Build rows: 1 row per phase, plus an "Unassigned / Header" row if needed
            row_phases = list(phases)
            has_unassigned = any(s.phase_id is None for s in stage_sensors)
            if has_unassigned or not row_phases:
                row_phases.append(None)  # None represents general/unassigned

            for phase in row_phases:
                phase_id = phase.pk if phase else None
                phase_name = phase.name if phase else "General / Plant-Wide"

                row = TelemetryRow(
                    phase_id=phase_id,
                    phase_name=phase_name,
                    cells={},
                )

                for param in distinct_params:
                    param_uuid = str(param.uuid)
                    slot_sensors = sensors_by_slot.get((stage_key, phase_id, param_uuid), [])

                    if not slot_sensors:
                        # No sensor configured for this slot
                        row.cells[param_uuid] = SensorCell(
                            parameter_id=param_uuid,
                            parameter_name=param.name,
                            unit=param.unit,
                            phase_name=phase_name,
                            status="no_sensor",
                            status_label="Unmonitored",
                        )
                        continue

                    # Select primary or first sensor
                    primary_sensor = slot_sensors[0]
                    measurement = latest_measurements.get(str(primary_sensor.uuid))

                    cell = SensorCell(
                        sensor_id=str(primary_sensor.uuid),
                        sensor_name=primary_sensor.name,
                        instrument_name=primary_sensor.instrument.name,
                        instrument_serial=primary_sensor.instrument.serial_number,
                        instrument_protocol=primary_sensor.instrument.get_protocol_display(),
                        instrument_status=primary_sensor.instrument.status,
                        phase_name=phase_name,
                        parameter_id=param_uuid,
                        parameter_name=param.name,
                        unit=primary_sensor.unit or param.unit,
                        min_detectable=primary_sensor.min_detectable,
                        max_detectable=primary_sensor.max_detectable,
                        redundant_count=max(0, len(slot_sensors) - 1),
                        is_primary=primary_sensor.is_primary,
                    )

                    if not measurement:
                        cell.status = "offline"
                        cell.status_label = "No Telemetry"
                        stage_group.alert_sensors += 1
                    else:
                        cell.value = measurement.value
                        cell.measured_at = measurement.measured_at
                        cell.time_ago = self.format_time_ago(measurement.measured_at)
                        cell.quality_flag = measurement.quality_flag
                        cell.drift_score = measurement.drift_score
                        cell.anomaly_score = measurement.anomaly_score
                        cell.signal_strength = measurement.signal_strength

                        # Precision formatting
                        if cell.value is not None:
                            # 2-3 decimal places cleanly
                            val_float = float(cell.value)
                            if abs(val_float) >= 100:
                                cell.formatted_value = f"{val_float:.1f}"
                            elif abs(val_float) >= 10:
                                cell.formatted_value = f"{val_float:.2f}"
                            else:
                                cell.formatted_value = f"{val_float:.3f}"

                        # Staleness and Instrument Health
                        age_sec = (now - measurement.measured_at).total_seconds()
                        expected_interval = primary_sensor.instrument.expected_heartbeat_sec * 3
                        is_stale = age_sec > expected_interval or age_sec > 900

                        # Check Range Bounds
                        if cell.value is not None:
                            if primary_sensor.min_detectable is not None and cell.value < primary_sensor.min_detectable:
                                cell.is_out_of_bounds = True
                            if primary_sensor.max_detectable is not None and cell.value > primary_sensor.max_detectable:
                                cell.is_out_of_bounds = True

                        # Determine Status
                        if primary_sensor.instrument.status in [
                            InstrumentStatus.OFFLINE,
                            InstrumentStatus.FAULT,
                        ]:
                            cell.status = "offline"
                            cell.status_label = f"Instrument {primary_sensor.instrument.get_status_display()}"
                            stage_group.alert_sensors += 1
                        elif is_stale:
                            cell.status = "stale"
                            cell.status_label = "Stale Telemetry"
                            stage_group.alert_sensors += 1
                        elif cell.is_out_of_bounds:
                            cell.status = "danger"
                            if cell.min_detectable is not None and cell.value < cell.min_detectable:
                                cell.status_label = f"Below Min ({cell.min_detectable})"
                            else:
                                cell.status_label = f"Above Max ({cell.max_detectable})"
                            stage_group.alert_sensors += 1
                        elif measurement.quality_flag == QualityFlag.INVALID:
                            cell.status = "danger"
                            cell.status_label = "Quality: Invalid"
                            stage_group.alert_sensors += 1
                        elif (
                            measurement.quality_flag in [QualityFlag.SUSPECT, QualityFlag.CALIBRATION]
                            or measurement.anomaly_score > 0.8
                        ):
                            cell.status = "warning"
                            cell.status_label = "Suspect Drift / Calib"
                            stage_group.alert_sensors += 1
                        else:
                            cell.status = "normal"
                            cell.status_label = "Normal (OK)"
                            stage_group.online_sensors += 1

                    row.cells[param_uuid] = cell

                stage_group.rows.append(row)

            stage_groups.append(stage_group)

        return sorted(stage_groups, key=lambda g: g.order)
