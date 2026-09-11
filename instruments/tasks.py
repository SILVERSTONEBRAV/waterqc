# instruments/tasks.py
import pytz
from decimal import Decimal
from datetime import timedelta
import logging
from celery import shared_task, Task
from django.utils import timezone
from django.db.models import Avg, Max, Min
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Sensor, Instrument, OnlineMeasurement, DerivedMetric, SensorHealthSnapshot
from alerts.engine import AlertEngine

logger = logging.getLogger("instruments.tasks")


# ============================================================
# 🔧 BASE TASK
# ============================================================
class BaseSensorTask(Task):
    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 5, 'countdown': 5}
    retry_backoff = True
    retry_backoff_max = 60

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {self.name} [{task_id}] failed: {exc}")
        super().on_failure(exc, task_id, args, kwargs, einfo)


# ============================================================
# 🧪 BULK SENSOR MEASUREMENTS
# ============================================================
@shared_task(bind=True, base=BaseSensorTask)
def process_sensor_measurements(self, data):
    """
    Bulk ingestion pipeline:
    - Validates readings & flags invalid/stale
    - Bulk inserts OnlineMeasurements
    - Updates derived metrics
    - Updates sensor health snapshot
    - Pushes threshold alerts to WebSocket
    """
    instrument_uuid = data.get("instrument_uuid")
    readings = data.get("readings", [])

    if not readings:
        return {"status": "no readings"}

    now = timezone.now()
    measurements_to_create = []
    alerts_to_send = []
    sensor_map = {}

    for r in readings:
        sensor_uuid = r.get("sensor_uuid")
        value = Decimal(r.get("value"))
        measured_at = r.get("measured_at")

        try:
            sensor = Sensor.objects.select_related('instrument').get(
                uuid=sensor_uuid, instrument__uuid=instrument_uuid, is_active=True
            )
            sensor_map[sensor_uuid] = sensor
        except Sensor.DoesNotExist:
            logger.warning(f"Sensor {sensor_uuid} not found for instrument {instrument_uuid}")
            continue

        try:
            measured_at_dt = timezone.datetime.fromisoformat(measured_at)
            if measured_at_dt.tzinfo is None:
                measured_at_dt = pytz.UTC.localize(measured_at_dt)
        except Exception:
            logger.warning(f"Invalid timestamp for sensor {sensor_uuid}: {measured_at}")
            continue

        flag = "ok"
        if (sensor.min_detectable is not None and value < sensor.min_detectable) or \
           (sensor.max_detectable is not None and value > sensor.max_detectable):
            flag = "invalid"

        age_sec = (now - measured_at_dt).total_seconds()
        if age_sec > sensor.instrument.expected_heartbeat_sec * 5:
            flag = "stale"

        if flag in ["invalid", "stale"]:
            alerts_to_send.append({
                "sensor_uuid": str(sensor.uuid),
                "value": str(value),
                "quality_flag": flag,
                "measured_at": measured_at_dt.isoformat()
            })

        measurements_to_create.append(
            OnlineMeasurement(
                sensor=sensor,
                value=value,
                measured_at=measured_at_dt,
                received_at=now,
                quality_flag=flag,
                treatment_plant=sensor.treatment_plant,
                phase=sensor.phase,
                signal_strength=r.get("signal_strength"),
                latency_ms=r.get("latency_ms"),
                raw_payload=r.get("raw_payload")
            )
        )

    if measurements_to_create:
        OnlineMeasurement.objects.bulk_create(measurements_to_create)
        logger.info(f"Inserted {len(measurements_to_create)} measurements for instrument {instrument_uuid}")

    # Derived metrics
    for sensor_uuid, sensor in sensor_map.items():
        sensor_measurements = OnlineMeasurement.objects.filter(
            sensor=sensor,
            measured_at__gte=now - timedelta(minutes=5),
            quality_flag='ok'
        )
        if sensor_measurements.exists():
            avg_val = sensor_measurements.aggregate(avg=Avg('value'))['avg']
            min_val = sensor_measurements.aggregate(min=Min('value'))['min']
            max_val = sensor_measurements.aggregate(max=Max('value'))['max']

            DerivedMetric.objects.bulk_create([
                DerivedMetric(
                    sensor=sensor,
                    metric_type='avg_5min',
                    value=avg_val,
                    window_start=now - timedelta(minutes=5),
                    window_end=now,
                    computed_at=now,
                    treatment_plant=sensor.treatment_plant,
                    phase=sensor.phase
                ),
                DerivedMetric(
                    sensor=sensor,
                    metric_type='min_5min',
                    value=min_val,
                    window_start=now - timedelta(minutes=5),
                    window_end=now,
                    computed_at=now,
                    treatment_plant=sensor.treatment_plant,
                    phase=sensor.phase
                ),
                DerivedMetric(
                    sensor=sensor,
                    metric_type='max_5min',
                    value=max_val,
                    window_start=now - timedelta(minutes=5),
                    window_end=now,
                    computed_at=now,
                    treatment_plant=sensor.treatment_plant,
                    phase=sensor.phase
                )
            ])

    # Sensor health snapshots
    for sensor in sensor_map.values():
        health_score = compute_sensor_health(sensor)
        SensorHealthSnapshot.objects.update_or_create(
            sensor=sensor,
            defaults={"health_score": health_score, "assessed_at": now, "reason": "bulk ingestion"}
        )

    # Push alerts
    if alerts_to_send:
        channel_layer = get_channel_layer()
        for alert in alerts_to_send:
            async_to_sync(channel_layer.group_send)(
                f"sensor_{alert['sensor_uuid']}",
                {"type": "sensor.alert", "message": alert}
            )

    return {
        "instrument_uuid": instrument_uuid,
        "processed_count": len(measurements_to_create),
        "alerts_sent": len(alerts_to_send),
        "timestamp": now.isoformat()
    }


# ============================================================
# ⚡ REAL-TIME SCADA DASHBOARD TASK
# ============================================================
@shared_task(bind=True, base=BaseSensorTask)
def push_scada_dashboard():
    """
    Periodically push all instrument + sensor status and health
    to WebSocket groups for a real-time SCADA dashboard.
    """
    now = timezone.now()
    instruments = Instrument.objects.prefetch_related('sensors').all()
    channel_layer = get_channel_layer()

    for instr in instruments:
        instr_data = {
            "uuid": str(instr.uuid),
            "name": instr.name,
            "status": instr.status,
            "last_seen": instr.last_seen.isoformat() if instr.last_seen else None,
            "sensors": []
        }

        for sensor in instr.sensors.all():
            # Latest health snapshot
            snapshot = SensorHealthSnapshot.objects.filter(sensor=sensor).order_by('-assessed_at').first()
            health_score = snapshot.health_score if snapshot else 0.5
            sensor_status = sensor.instrument.status if sensor.instrument else "offline"

            # Color coding
            if sensor_status == "online" and health_score > 0.7:
                color = "green"
            elif sensor_status == "degraded" or health_score <= 0.7:
                color = "yellow"
            else:
                color = "red"

            instr_data["sensors"].append({
                "uuid": str(sensor.uuid),
                "name": sensor.name,
                "parameter": sensor.parameter.name,
                "stage": sensor.stage,
                "status": sensor_status,
                "health_score": float(health_score),
                "color": color
            })

        # Push to WebSocket group per instrument
        async_to_sync(channel_layer.group_send)(
            f"instrument_{instr.uuid}",
            {
                "type": "scada.update",
                "message": instr_data
            }
        )

    logger.info(f"SCADA dashboard updated at {now.isoformat()}")


# ============================================================
# 🔮 SENSOR HEALTH COMPUTATION
# ============================================================
def compute_sensor_health(sensor: Sensor) -> float:
    recent = OnlineMeasurement.objects.filter(
        sensor=sensor,
        measured_at__gte=timezone.now() - timedelta(hours=24)
    )
    if not recent.exists():
        return 0.5  # unknown

    stale_count = recent.filter(quality_flag='stale').count()
    invalid_count = recent.filter(quality_flag='invalid').count()
    total = recent.count()
    score = 1.0 - (stale_count + invalid_count) / total
    return max(0.0, min(1.0, score))
