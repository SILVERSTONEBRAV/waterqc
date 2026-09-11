#backwashing/models.py
from django.db import models
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP


class OperationStatus(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('delayed', 'Delayed'),
        ('cancelled', 'Cancelled'),
    ]
    name = models.CharField(max_length=50, choices=STATUS_CHOICES, unique=True)

    def __str__(self):
        return self.get_name_display()


class PhaseLossRate(models.Model):
    OPERATION_CHOICES = [
        ('backwashing', 'Backwashing'),
        ('disludging', 'Disludging'),
        ('flushing', 'Flushing'),
    ]

    phase = models.ForeignKey('t.TreatmentPlantPhase', on_delete=models.CASCADE, related_name='loss_rates')
    operation = models.CharField(max_length=20, choices=OPERATION_CHOICES)
    loss_rate_m3pm = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        help_text="Water loss rate in cubic meters per minute (m³/min)."
    )
    effective_date = models.DateField(default=timezone.now)

    class Meta:
        unique_together = ('phase', 'operation')
        verbose_name = "Phase Loss Rate"
        verbose_name_plural = "Phase Loss Rates"

    def __str__(self):
        return f"{self.phase} - {self.operation} - {self.loss_rate_m3pm} m³/min"


class Backwashing(models.Model):
    treatment_plant = models.ForeignKey('t.TreatmentPlant', on_delete=models.CASCADE)
    phase = models.ForeignKey('t.TreatmentPlantPhase', on_delete=models.SET_NULL, null=True, blank=True, related_name='backwashing_operations')
    filter_unit = models.ForeignKey('t.WaterFilter', on_delete=models.CASCADE, related_name='backwashing_operations')
    performed_by = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, related_name='backwashing_done')
    shift_assignment = models.ForeignKey('sc.ShiftAssignment', on_delete=models.SET_NULL, null=True, blank=True, related_name='backwashing_logs')

    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)

    water_lost_m3 = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Volume of water lost (in cubic meters)."
    )

    remarks = models.TextField(blank=True)
    status = models.ForeignKey('OperationStatus', on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"Backwashing - {self.filter_unit} ({self.start_time.date()})"

    @property
    def duration_minutes(self):
        if self.end_time and self.start_time:
            delta = self.end_time - self.start_time
            return int(delta.total_seconds() / 60)
        return None

    def save(self, *args, **kwargs):
        if self.end_time and self.start_time and self.phase:
            from .models import PhaseLossRate
            try:
                rate = PhaseLossRate.objects.get(phase=self.phase, operation='backwashing')
                self.water_lost_m3 = (Decimal(self.duration_minutes) * rate.loss_rate_m3pm).quantize(
                    Decimal('0.001'), rounding=ROUND_HALF_UP
                )
            except PhaseLossRate.DoesNotExist:
                self.water_lost_m3 = Decimal("0.000")
        super().save(*args, **kwargs)


class Disludging(models.Model):
    treatment_plant = models.ForeignKey('t.TreatmentPlant', on_delete=models.CASCADE)
    phase = models.ForeignKey('t.TreatmentPlantPhase', on_delete=models.SET_NULL, null=True, blank=True, related_name='disludging_operations')
    clarifier = models.ForeignKey('t.Clarifier', on_delete=models.CASCADE, related_name='disludging_operations')
    performed_by = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, related_name='disludging_done')
    shift_assignment = models.ForeignKey('sc.ShiftAssignment', on_delete=models.SET_NULL, null=True, blank=True, related_name='disludging_logs')

    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)

    water_lost_m3 = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Volume of water lost (in cubic meters)."
    )

    remarks = models.TextField(blank=True)
    status = models.ForeignKey('OperationStatus', on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"Disludging - {self.clarifier} ({self.start_time.date()})"

    @property
    def duration_minutes(self):
        if self.end_time and self.start_time:
            delta = self.end_time - self.start_time
            return int(delta.total_seconds() / 60)
        return None

    def save(self, *args, **kwargs):
        if self.end_time and self.start_time and self.phase and self.clarifier:
            from .models import PhaseLossRate
            try:
                rate = PhaseLossRate.objects.get(phase=self.phase, operation='disludging')
                valve_count = self.clarifier.disludge_valves.count()
                if valve_count > 0 and self.duration_minutes:
                    total_loss = Decimal(self.duration_minutes) * rate.loss_rate_m3pm * Decimal(valve_count)
                    self.water_lost_m3 = total_loss.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                else:
                    self.water_lost_m3 = Decimal("0.000")
            except PhaseLossRate.DoesNotExist:
                self.water_lost_m3 = Decimal("0.000")
        super().save(*args, **kwargs)


class PumpFlush(models.Model):
    treatment_plant = models.ForeignKey('t.TreatmentPlant', on_delete=models.CASCADE)
    phase = models.ForeignKey('t.TreatmentPlantPhase', on_delete=models.SET_NULL, null=True, blank=True, related_name='pump_flush_operations')
    chemical_pump = models.ForeignKey('o.ChemicalPump', on_delete=models.CASCADE, related_name='flush_logs')
    performed_by = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, related_name='flush_operations')
    shift_assignment = models.ForeignKey('sc.ShiftAssignment', on_delete=models.SET_NULL, null=True, blank=True, related_name='flush_logs')

    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)

    water_lost_m3 = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Volume of water lost (in cubic meters)."
    )

    remarks = models.TextField(blank=True)
    status = models.ForeignKey('OperationStatus', on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"Flush - {self.chemical_pump} ({self.start_time.date()})"

    @property
    def duration_minutes(self):
        if self.end_time and self.start_time:
            delta = self.end_time - self.start_time
            return int(delta.total_seconds() / 60)
        return None

    def save(self, *args, **kwargs):
        if self.end_time and self.start_time and self.phase:
            from .models import PhaseLossRate
            try:
                rate = PhaseLossRate.objects.get(phase=self.phase, operation='flushing')
                self.water_lost_m3 = (Decimal(self.duration_minutes) * rate.loss_rate_m3pm).quantize(
                    Decimal('0.001'), rounding=ROUND_HALF_UP
                )
            except PhaseLossRate.DoesNotExist:
                self.water_lost_m3 = Decimal("0.000")
        super().save(*args, **kwargs)
