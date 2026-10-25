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
            AlertEngine.auto_escalate_unacknowledged(instance=instance)


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
        AlertEngine.auto_escalate_unacknowledged(instance=instance)


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
    today = timezone.localdate()
    alert_types = []

    maint_date = getattr(instance, 'next_maintenance_date', None)
    if maint_date:
        if hasattr(maint_date, 'date'):
            maint_date = maint_date.date()
        if maint_date <= today:
            alert_types.append('maintenance_due')

    calib_date = getattr(instance, 'calibration_due_date', None)
    if calib_date:
        if hasattr(calib_date, 'date'):
            calib_date = calib_date.date()
        if calib_date <= today:
            alert_types.append('verification_pending')

    for alert_type in alert_types:
        AlertEngine.trigger_alert(instance, alert_type=alert_type)
        AlertEngine.auto_escalate_unacknowledged(instance=instance)


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


# ============================================================
# 🎙️ UNIVERSAL VOICE MESSAGE GENERATION FOR ALL ALERTS & NOTIFICATIONS
# ============================================================

AlertState = apps.get_model('alerts', 'AlertState')


@receiver(post_save, sender=AlertState)
def handle_alert_state_voice(sender, instance, created, **kwargs):
    """Ensure every AlertState record has a corresponding persistent VoiceAlert."""
    if created:
        try:
            from alerts.models import VoiceAlert
            if not VoiceAlert.objects.filter(alert_state=instance).exists():
                cfg = instance.alert_config
                body = (cfg.template.body_template if cfg and cfg.template else None) or f"Alert state {instance.state} for {instance.instance_ref}"
                title = cfg.alert_type if cfg else "System Alert Notification"
                VoiceAlert.generate_persistent_voice_alert(
                    message=body,
                    title=title,
                    alert_config=cfg,
                    alert_state=instance,
                )
        except Exception as e:
            logger.warning(f"[VoiceAlert] AlertState signal voice generation notice: {e}")


try:
    ChemicalWorkflowAlert = apps.get_model('ca', 'ChemicalWorkflowAlert')

    @receiver(post_save, sender=ChemicalWorkflowAlert)
    def handle_ca_workflow_alert_voice(sender, instance, created, **kwargs):
        """Ensure every CA workflow alert generates a corresponding voice message."""
        if created:
            try:
                from alerts.models import VoiceAlert
                from datetime import timedelta
                # Deduplicate by title & recent window to avoid duplicate voice per recipient in batch notifications
                recent_window = timezone.now() - timedelta(seconds=15)
                if not VoiceAlert.objects.filter(title=instance.title, created_at__gte=recent_window).exists():
                    voice_text = f"{instance.title}. {instance.message}"
                    VoiceAlert.generate_persistent_voice_alert(
                        message=voice_text,
                        title=instance.title,
                    )
            except Exception as e:
                logger.warning(f"[VoiceAlert] CA workflow alert signal voice generation notice: {e}")
except Exception:
    pass
