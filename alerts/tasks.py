# alerts/tasks.py
import logging
from datetime import date, datetime
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.mail import send_mail
from celery import shared_task
from celery.utils.log import get_task_logger
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.apps import apps
import asyncio

from .utils import (
    generate_voice_notification_pyttsx3,
    SMSSender,
    WhatsAppSender,
    SlackNotifier,
    InstanceSerializer,
    SafeConditionEvaluator,
    AIAlertPriorityPredictor,
    GeoContextAnalyzer,
)

logger = get_task_logger(__name__)

# =========================================
# 🔹 Helper: Filter recipients by preferences & scope
# =========================================
def filter_recipients(recipients, message_type="email", treatment_plant=None, group=None, section=None):
    """
    Filters users based on:
    - UserAlertPreference
    - Treatment plant
    - Group membership
    - Section
    """
    filtered = []
    for user in recipients:
        pref = getattr(user, "alert_preferences", None)
        if pref and not getattr(pref, f"receive_{message_type}", True):
            continue
        # Scope checks
        if treatment_plant and getattr(user, "treatment_plant", None) != treatment_plant:
            continue
        if group and group not in getattr(user, "groups", []):
            continue
        if section and getattr(user, "section", None) != section:
            continue
        filtered.append(user)
    return filtered

# =========================================
# 🔹 Async multi-channel alert dispatcher
# =========================================
async def _dispatch_alerts_async(subject, body, recipients, treatment_plant=None, group=None, section=None, context=None):
    """
    Asynchronously dispatch alerts across multiple channels.
    Respects user preferences and scopes.
    """
    tasks = []

    for user in recipients:
        # Filter by scope
        if user not in filter_recipients([user], "email", treatment_plant, group, section):
            continue

        # Optional safe condition check
        if context and not SafeConditionEvaluator.evaluate(user, context):
            continue

        # Email
        if getattr(user, "email", None):
            tasks.append(asyncio.to_thread(send_mail, subject, body, settings.DEFAULT_FROM_EMAIL, [user.email]))

        # SMS
        if getattr(user, "phone_number", None):
            tasks.append(SMSSender.send_sms(user.phone_number, body))

        # WhatsApp
        if getattr(user, "whatsapp_number", None):
            tasks.append(WhatsAppSender.send_message(user.whatsapp_number, body))

        # Slack
        if getattr(user, "slack_channel", None):
            tasks.append(SlackNotifier.send_message(user.slack_channel, body))

        # Push/WebSocket
        channel_layer = get_channel_layer()
        tasks.append(asyncio.to_thread(async_to_sync, channel_layer.group_send)(
            f"user_{user.id}_alerts",
            {"type": "alert.message", "message": body}
        ))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Alert dispatch exception: {r}")



# =========================================
# 🔹 WebSocket Alerts
# =========================================
@shared_task
def send_websocket_notification(message, group="alerts_group"):
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            group,
            {"type": "alert.message", "message": message}
        )
        logger.info(f"WebSocket alert sent to group {group}")
    except Exception as e:
        logger.error(f"Failed to send WebSocket alert: {e}")


# =========================================
# 🔹 Celery wrapper for async dispatcher
# =========================================
@shared_task
def dispatch_alerts(subject=None, body=None, recipients=None,
                    treatment_plant=None, group=None, section=None, context=None):
    """
    Celery entrypoint for dispatching alerts.
    Required args: subject, body, recipients (list of User objects).
    """
    if not subject or not body or not recipients:
        logger.warning("dispatch_alerts called without required arguments: "
                       f"subject={subject}, body={body}, recipients={recipients}")
        return

    try:
        asyncio.run(
            _dispatch_alerts_async(subject, body, recipients,
                                   treatment_plant, group, section, context)
        )
        logger.info(f"Dispatched alerts to {len(recipients)} recipients "
                    f"(plant={treatment_plant}, group={group}, section={section})")
    except Exception as e:
        logger.exception(f"Failed to dispatch alerts: {e}")


# =========================================
# 🔹 Voice notification
# =========================================
@shared_task
def generate_voice_notification(message):
    try:
        file_path = generate_voice_notification_pyttsx3(message)
        logger.info(f"Voice notification generated at {file_path}")
        return file_path
    except Exception as e:
        logger.exception(f"Failed to generate voice notification: {e}")

# =========================================
# 🔹 Alarm trigger
# =========================================
@shared_task
def trigger_alarm(user_id, message, alarm_sound_path=None):
    alarm_sound_path = alarm_sound_path or "/static/path/to/alarm_sound.mp3"
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}_alerts",
            {"type": "trigger_alarm", "message": message, "alarm_sound": alarm_sound_path}
        )
        logger.info(f"Alarm triggered for user {user_id}")
    except Exception as e:
        logger.exception(f"Failed to trigger alarm for user {user_id}: {e}")

# =========================================
# 🔹 Repeat alarms until acknowledged
# =========================================
@shared_task(bind=True)
def repeat_alarm_until_acknowledged(self, user_id, alert_config_id, instance_model, instance_id,
                                    interval_sec=30, max_repeats=20):
    try:
        AlarmAcknowledgment = apps.get_model("alerts", "AlarmAcknowledgment")
        AlertConfig = apps.get_model("alerts", "AlertConfig")
        AlertState = apps.get_model("alerts", "AlertState")

        model_map = {
            "qc": "qc.NonConformity",
            "heavymetal": "heavy_metal.HeavyMetalNonConformity",
            "microbial": "microbial.NonConformity",
            "inventory": "inventory.NonConformity"
        }
        InstanceModel = apps.get_model(*model_map[instance_model].split("."))
        instance = InstanceModel.objects.get(id=instance_id)
        alert_config = AlertConfig.objects.get(id=alert_config_id)

        # Stop if acknowledged
        ack = AlarmAcknowledgment.objects.filter(
            user_id=user_id,
            content_type__model=InstanceModel._meta.model_name,
            object_id=instance_id
        ).first()
        if ack and ack.acknowledged:
            logger.info(f"User {user_id} acknowledged instance {instance_id}. Stopping repeat alarms.")
            return

        serialized = InstanceSerializer.serialize(instance)

        # AI-prioritized
        predicted_priority = AIAlertPriorityPredictor.predict(serialized)
        if predicted_priority != alert_config.priority:
            alert_config.priority = predicted_priority
            alert_config.save(update_fields=['priority'])

        # Contextual info
        context = GeoContextAnalyzer.enrich(serialized)

        # Scope
        treatment_plant = getattr(instance, "treatment_plant", None)
        section = getattr(instance, "section", None)
        group = getattr(instance, "group", None)

        subject = alert_config.template.subject_template.format(**serialized)
        body = alert_config.template.body_template.format(**serialized)
        recipients = list(alert_config.recipients.all())

        # Dispatch alerts with dynamic scope and AI context
        dispatch_alerts.delay(subject, body, recipients,
                              treatment_plant=treatment_plant, group=group, section=section, context=context)

        if getattr(alert_config.template, "auto_voice_enabled", False):
            generate_voice_notification.delay(body)

        trigger_alarm.delay(user_id, message=body)

        # Update alert state
        AlertState.objects.update_or_create(
            alert_config=alert_config,
            instance_ref=str(instance.id),
            defaults={"state": AlertState.StateChoices.QUEUED}
        )

        # Reschedule with max repeats
        if self.request.retries < max_repeats:
            self.apply_async(
                args=[user_id, alert_config_id, instance_model, instance_id, interval_sec, max_repeats],
                countdown=interval_sec
            )
            logger.info(f"Repeat alarm scheduled in {interval_sec}s for user {user_id}")
        else:
            logger.warning(f"Max repeats reached for user {user_id} on instance {instance_id}")

    except Exception as e:
        logger.exception(f"Error in repeat_alarm_until_acknowledged: {e}")

# =========================================
# 🔹 Escalation task (unchanged except logging clarity)
# =========================================
@shared_task
def escalate_alert(alert_config_id, instance_model, instance_id):
    try:
        AlertConfig = apps.get_model("alerts", "AlertConfig")
        model_map = {
            "qc": "qc.NonConformity",
            "heavymetal": "heavy_metal.HeavyMetalNonConformity",
            "microbial": "microbial.NonConformity",
            "inventory": "inventory.NonConformity"
        }
        InstanceModel = apps.get_model(*model_map[instance_model].split("."))
        instance = InstanceModel.objects.get(id=instance_id)
        alert_config = AlertConfig.objects.get(id=alert_config_id)

        if getattr(instance, "acknowledged", False):
            logger.info(f"Instance {instance_id} already acknowledged, skipping escalation.")
            return

        serialized = InstanceSerializer.serialize(instance)

        subject = f"Escalated: {alert_config.template.subject_template.format(**serialized)}"
        body = f"Escalated: {alert_config.template.body_template.format(**serialized)}"
        recipients = [alert_config.escalate_to] if alert_config.escalate_to else list(alert_config.recipients.all())

        dispatch_alerts.delay(subject, body, recipients,
                              treatment_plant=getattr(instance, "treatment_plant", None),
                              group=getattr(instance, "group", None),
                              section=getattr(instance, "section", None))
        logger.info(f"Escalation triggered for {instance_model} id {instance_id}")

    except Exception as e:
        logger.exception(f"Error in escalate_alert: {e}")

# =========================================
# 🔹 QC / HeavyMetal / Microbial Auto-Generation Engine
# =========================================
from qc.models import SamplingSchedule, WaterAnalysis
from heavy_metal.models import HeavyMetalAnalysis
from microbial.models import MicrobialAnalysis

ANALYSIS_MODEL_MAP = {
    "water": WaterAnalysis,
    "heavymetal": HeavyMetalAnalysis,
    "microbial": MicrobialAnalysis,
}

def _analysis_exists(model, plant, analysis_time):
    return model.objects.filter(treatment_plant=plant, analysis_time=analysis_time).exists()

def _build_analysis_instance(schedule, analysis_time):
    model = ANALYSIS_MODEL_MAP[schedule.analysis_type]
    kwargs = {
        "treatment_plant": schedule.treatment_plant,
        "analysis_time": analysis_time,
    }
    if hasattr(model, "treatment_plant_phase"):
        kwargs["treatment_plant_phase"] = schedule.treatment_plant_phase
    if hasattr(model, "shift") and schedule.shift:
        kwargs["shift"] = schedule.shift
    if hasattr(model, "method") and hasattr(schedule, "method"):
        kwargs["method"] = schedule.method
    return model(**kwargs)

# =========================================
# 🔹 Scheduled Analyses Generator (patch)
# =========================================
@shared_task
def generate_scheduled_analyses(run_date=None):
    run_date = run_date or date.today()
    schedules = (
        SamplingSchedule.objects
        .filter(active=True)
        .select_related("treatment_plant", "treatment_plant_phase", "shift")
        .prefetch_related("times")
    )

    AlertConfig = apps.get_model("alerts", "AlertConfig")

    with transaction.atomic():
        for schedule in schedules:
            model = ANALYSIS_MODEL_MAP.get(schedule.analysis_type)
            if not model:
                logger.warning(f"Unknown analysis_type={schedule.analysis_type} in schedule {schedule.id}")
                continue

            for sampling_time in schedule.times.all():
                analysis_time = timezone.make_aware(datetime.combine(run_date, sampling_time.time))
                if _analysis_exists(model, schedule.treatment_plant, analysis_time):
                    continue

                instance = _build_analysis_instance(schedule, analysis_time)
                instance.save()
                logger.info(f"Generated analysis {model.__name__} for {schedule.treatment_plant} at {analysis_time}")

                # Trigger alerts for relevant plant/section/group
                for alert_config in AlertConfig.objects.filter(active=True):
                    recipients = list(alert_config.recipients.all())
                    if not recipients:
                        continue
                    dispatch_alerts.delay(
                        subject=f"Scheduled Analysis Generated: {model.__name__}",
                        body=f"Analysis for {schedule.treatment_plant} at {analysis_time} has been created.",
                        recipients=recipients,
                        treatment_plant=schedule.treatment_plant,
                        section=getattr(schedule, "section", None),
                        group=getattr(schedule, "group", None)
                    )
