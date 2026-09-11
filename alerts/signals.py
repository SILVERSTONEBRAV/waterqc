# alerts/signals.py
import logging
from django.apps import apps
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone

from .engine import AlertEngine  # centralized alert system

logger = logging.getLogger(__name__)


# ============================================================
# ⚡ Utility: Store previous state before save
# ============================================================
def store_previous_state(instance):
    """
    Attach previous state to instance to detect state transitions.
    """
    model_class = type(instance)
    if instance.pk:
        try:
            instance._previous_state = model_class.objects.get(pk=instance.pk).state
        except model_class.DoesNotExist:
            instance._previous_state = None
    else:
        instance._previous_state = None


# ============================================================
# 🚨 Generic NonConformity Alert Registration
# ============================================================
def register_nc_alerts(app_label, model_name):
    """
    Dynamically register post_save signal for NonConformity-like models.
    Avoids circular imports.
    """
    model = apps.get_model(app_label, model_name)

    @receiver(post_save, sender=model)
    def _handle_nc_save(sender, instance, created, **kwargs):
        if created:
            AlertEngine.trigger_alert(instance, alert_type='nonconformity')
            AlertEngine.auto_escalate_unacknowledged(instance)


# Register all NonConformity models dynamically
for app_model in [
    ('qc', 'NonConformity'),
    ('heavy_metal', 'HeavyMetalNonConformity'),
    ('microbial', 'MicrobialNonConformity'),
]:
    register_nc_alerts(*app_model)


# ============================================================
# 🔹 WaterAnalysis Auto-Transition Alerts
# ============================================================
WaterAnalysis = apps.get_model('qc', 'WaterAnalysis')


@receiver(pre_save, sender=WaterAnalysis)
def store_water_analysis_state(sender, instance, **kwargs):
    store_previous_state(instance)


@receiver(post_save, sender=WaterAnalysis)
def handle_water_analysis_save(sender, instance, created, **kwargs):
    """
    Trigger alerts when WaterAnalysis transitions to VERIFIED or CONFIRMED.
    """
    if created:
        return

    state_transitions_for_alert = ['verified', 'confirmed']
    previous = getattr(instance, "_previous_state", None)

    if previous != instance.state and instance.state.lower() in state_transitions_for_alert:
        AlertEngine.trigger_alert(instance, alert_type='auto_verification')
        AlertEngine.auto_escalate_unacknowledged(instance)


# ============================================================
# 🛠️ Equipment Maintenance & Calibration Alerts
# ============================================================
Equipment = apps.get_model('inventory', 'Equipment')


@receiver(post_save, sender=Equipment)
def handle_equipment_save(sender, instance, created, **kwargs):
    """Check maintenance and calibration due dates, trigger alerts, auto-escalate."""
    check_and_trigger_equipment_alerts(instance)


def check_and_trigger_equipment_alerts(instance):
    """Trigger maintenance/calibration alerts if due."""
    now = timezone.now()
    alert_types = []

    if getattr(instance, 'next_maintenance_date', None) and instance.next_maintenance_date <= now:
        alert_types.append('maintenance_due')

    if getattr(instance, 'calibration_due_date', None) and instance.calibration_due_date <= now:
        alert_types.append('verification_pending')

    for alert_type in alert_types:
        AlertEngine.trigger_alert(instance, alert_type=alert_type)
        AlertEngine.auto_escalate_unacknowledged(instance)


# ============================================================
# ⚡ Generic Helper for Manual Alert Trigger
# ============================================================
def dynamic_alert_trigger(instance, alert_type):
    """
    Centralized alert helper:
      - AI-based priority prediction
      - Multi-channel dispatch (email, push, voice)
      - Auto-escalation if unacknowledged
    """
    try:
        AlertEngine.trigger_alert(instance, alert_type=alert_type)
        AlertEngine.auto_escalate_unacknowledged(instance)
        logger.info(f"✅ Alert triggered for {alert_type} on {instance}")
    except Exception as e:
        logger.exception(f"❌ Failed to trigger alert for {alert_type} on {instance}: {e}")
