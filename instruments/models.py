# instruments/models.py
import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError

from t.models import TreatmentPlant, TreatmentPlantPhase
from parameters.models import PhysicochemicalParameter, ParameterUnit

# =====================================================
# Treatment Stages
# =====================================================
class TreatmentStage(models.TextChoices):
    RAW_WATER = 'raw_water', 'Raw Water'
    COAGULATED = 'coagulated', 'Coagulated Water'
    CLARIFIED = 'clarified', 'Clarified Water'
    FILTERED = 'filtered', 'Filtered Water'
    TREATED = 'treated', 'Treated Water'


# =====================================================
# Enumerations
# =====================================================
class InstrumentProtocol(models.TextChoices):
    HTTP = 'http', 'HTTP / REST'
    MQTT = 'mqtt', 'MQTT'
    MODBUS = 'modbus', 'Modbus TCP'
    OPCUA = 'opcua', 'OPC-UA'


class InstrumentStatus(models.TextChoices):
    ONLINE = 'online', 'Online'
    OFFLINE = 'offline', 'Offline'
    DEGRADED = 'degraded', 'Degraded'
    FAULT = 'fault', 'Fault'
    MAINTENANCE = 'maintenance', 'Maintenance'


class QualityFlag(models.TextChoices):
    OK = 'ok', 'OK'
    SUSPECT = 'suspect', 'Suspect'
    INVALID = 'invalid', 'Invalid'
    STALE = 'stale', 'Stale'
    CALIBRATION = 'calibration', 'Calibration Required'


# =====================================================
# Instrument (Gateway / PLC / Controller)
# =====================================================
class Instrument(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=120)
    manufacturer = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=120, blank=True)
    serial_number = models.CharField(max_length=120, unique=True)

    treatment_plant = models.ForeignKey(
        TreatmentPlant, on_delete=models.CASCADE, related_name='instruments'
    )
    phase = models.ForeignKey(
        TreatmentPlantPhase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instruments'
    )

    protocol = models.CharField(max_length=20, choices=InstrumentProtocol.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    mac_address = models.CharField(max_length=32, blank=True)
    firmware_version = models.CharField(max_length=50, blank=True)

    status = models.CharField(
        max_length=20,
        choices=InstrumentStatus.choices,
        default=InstrumentStatus.OFFLINE
    )
    last_seen = models.DateTimeField(null=True, blank=True)
    installed_at = models.DateField()
    expected_heartbeat_sec = models.PositiveIntegerField(default=60)

    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['treatment_plant', 'status']),
            models.Index(fields=['last_seen']),
        ]

    # -------------------------
    # Health Logic
    # -------------------------
    def heartbeat(self):
        """Called by ingestion layer or MQTT consumer"""
        self.last_seen = timezone.now()
        self.status = InstrumentStatus.ONLINE
        self.save(update_fields=["last_seen", "status"])

    def is_stale(self) -> bool:
        if not self.last_seen:
            return True
        age = (timezone.now() - self.last_seen).total_seconds()
        return age > self.expected_heartbeat_sec * 3

    def refresh_health(self):
        if self.is_stale() and self.status == InstrumentStatus.ONLINE:
            self.status = InstrumentStatus.DEGRADED
            self.save(update_fields=["status"])

    def __str__(self):
        return f"{self.name} [{self.serial_number}]"


# =====================================================
# Sensor / Probe
# =====================================================
class Sensor(models.Model):
    """
    Physical probe attached to an Instrument.
    Context (plant + phase) is inherited automatically.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    instrument = models.ForeignKey(
        Instrument, on_delete=models.CASCADE, related_name='sensors'
    )

    name = models.CharField(max_length=100)
    parameter = models.ForeignKey(PhysicochemicalParameter, on_delete=models.CASCADE)
    stage = models.CharField(max_length=20, choices=TreatmentStage.choices)
    unit = models.CharField(max_length=20, choices=ParameterUnit.choices)

    min_detectable = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True
    )
    max_detectable = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True
    )

    drift_threshold = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Allowed change from rolling average before SUSPECT"
    )

    is_primary = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.CASCADE,
        editable=False,
        null=True,
        blank=True,
        related_name='sensors'
    )
    phase = models.ForeignKey(
        TreatmentPlantPhase,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        blank=True,
        related_name='sensors'
    )

    class Meta:
        unique_together = (
            'instrument',
            'parameter',
            'stage',
            'name',
        )
        indexes = [
            models.Index(fields=['instrument', 'stage']),
            models.Index(fields=['treatment_plant', 'parameter']),
        ]

    def clean(self):
        if self.unit != self.parameter.unit:
            raise ValidationError(
                f"Unit mismatch: sensor={self.unit}, parameter={self.parameter.unit}"
            )

    def save(self, *args, **kwargs):
        self.treatment_plant = self.instrument.treatment_plant
        self.phase = self.instrument.phase
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.parameter.name} ({self.stage})"


class OnlineMeasurement(models.Model):
    """
    Event-sourced immutable telemetry stream.
    """

    id = models.BigAutoField(primary_key=True)

    sensor = models.ForeignKey(
        Sensor,
        on_delete=models.CASCADE,
        related_name='measurements'
    )

    value = models.DecimalField(max_digits=16, decimal_places=5)

    measured_at = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.CASCADE,
        editable=False,
        related_name='measurements'
    )

    phase = models.ForeignKey(
        TreatmentPlantPhase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='measurements'
    )

    quality_flag = models.CharField(
        max_length=20,
        choices=QualityFlag.choices,
        default=QualityFlag.OK,
        db_index=True
    )

    anomaly_score = models.FloatField(default=0.0)
    drift_score = models.FloatField(default=0.0)

    signal_strength = models.IntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)

    raw_payload = models.JSONField(null=True, blank=True)

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source = models.CharField(max_length=50, default="mqtt")

    class Meta:
        ordering = ['-measured_at']

        indexes = [
            models.Index(fields=['sensor', 'measured_at']),
            models.Index(fields=['treatment_plant', 'measured_at']),
            models.Index(fields=['quality_flag', 'measured_at']),
            models.Index(fields=['event_id']),
        ]

        constraints = [
            # FIXED Django 4/5 syntax
            models.CheckConstraint(
                name='measurement_value_not_null',
                condition=Q(value__isnull=False),
            ),

            models.CheckConstraint(
                name='measurement_value_range_safe',
                condition=Q(value__gte=-1e12) & Q(value__lte=1e12),
            ),
        ]

    # -------------------------
    # QUALITY ENGINE
    # -------------------------
    def apply_quality_checks(self):
        s = self.sensor

        if self.value is None:
            self.quality_flag = QualityFlag.INVALID
            return

        if s.min_detectable is not None and self.value < s.min_detectable:
            self.quality_flag = QualityFlag.INVALID

        elif s.max_detectable is not None and self.value > s.max_detectable:
            self.quality_flag = QualityFlag.INVALID

        elif self.signal_strength is not None and self.signal_strength < 10:
            self.quality_flag = QualityFlag.SUSPECT

        elif self.anomaly_score is not None and self.anomaly_score > 0.8:
            self.quality_flag = QualityFlag.SUSPECT

    # -------------------------
    # SAVE PIPELINE
    # -------------------------
    def save(self, *args, **kwargs):
        self.treatment_plant = self.sensor.treatment_plant
        self.phase = self.sensor.phase

        self.apply_quality_checks()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.value} [{self.sensor.unit}]"


# =====================================================
# Derived Metrics (Aggregates / KPIs)
# =====================================================
class DerivedMetric(models.Model):
    """
    Computed values (rolling means, medians, alarms).
    Safe for dashboards & alerts.
    """

    sensor = models.ForeignKey(
        Sensor, on_delete=models.CASCADE, related_name='derived_metrics'
    )

    metric_type = models.CharField(
        max_length=50,
        help_text="avg_5min, avg_1hr, max_24h, median_15min"
    )
    value = models.DecimalField(max_digits=16, decimal_places=5)

    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    computed_at = models.DateTimeField(auto_now_add=True)

    treatment_plant = models.ForeignKey(
        TreatmentPlant,
        on_delete=models.CASCADE,
        editable=False,
        null=True,
        blank=True,
        related_name='derived_metrics'
    )
    phase = models.ForeignKey(
        TreatmentPlantPhase,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        blank=True,
        related_name='derived_metrics'
    )

    class Meta:
        indexes = [
            models.Index(fields=['sensor', 'metric_type']),
            models.Index(fields=['window_end']),
        ]

    def save(self, *args, **kwargs):
        self.treatment_plant = self.sensor.treatment_plant
        self.phase = self.sensor.phase
        super().save(*args, **kwargs)


# =====================================================
# Calibration
# =====================================================
class InstrumentCalibration(models.Model):
    instrument = models.ForeignKey(
        Instrument, on_delete=models.CASCADE, related_name='calibrations'
    )

    performed_at = models.DateTimeField(default=timezone.now)
    performed_by = models.CharField(max_length=100)
    method = models.CharField(max_length=100)

    valid_until = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-performed_at']
        indexes = [models.Index(fields=['valid_until'])]

    def is_expired(self):
        return timezone.now().date() > self.valid_until

    def __str__(self):
        return f"Calibration {self.instrument.serial_number}"


# =====================================================
# Sensor Health Snapshot
# =====================================================
class SensorHealthSnapshot(models.Model):
    """
    Periodic confidence score (AI / rules / QC).
    """

    sensor = models.ForeignKey(
        Sensor, on_delete=models.CASCADE, related_name='health_snapshots'
    )

    health_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="0–100 confidence score"
    )
    assessed_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-assessed_at']
        indexes = [
            models.Index(fields=['sensor', 'assessed_at']),
            models.Index(fields=['health_score']),
        ]

    def __str__(self):
        return f"{self.sensor} → {self.health_score}%"
