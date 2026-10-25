import logging
from django.utils import timezone
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import AlertConfig, AlertState, AlertLog
from .utils import (
    InstanceSerializer,
    SafeConditionEvaluator,
    AIAlertPriorityPredictor,
    GeoContextAnalyzer,
)
from .tasks import (
    dispatch_alerts,
    generate_voice_notification,
    send_websocket_notification,
    escalate_alert,
)

logger = logging.getLogger(__name__)

class AlertEngine:
    """
    Advanced Alert Engine for multi-app integration.
    Features:
        - AI-priority prediction
        - Geo-context aware routing
        - Multi-channel dispatch (email, SMS, push, Slack, voice)
        - Escalation and retry logic
        - Real-time websocket notifications
        - Audit/Alert logging
        - Full signal and instrumentation integration
    """

    @staticmethod
    def trigger_alert(instance, alert_types=None, alert_type=None, audit_notes=None):
        """
        Trigger alerts relevant to an instance.
        - `alert_types`: list of alert_type strings to filter alerts (preferred)
        - `alert_type`:  single alert_type string — convenience alias for signals
        - `audit_notes`: optional notes for logs
        """
        # Normalise: accept either singular or plural kwarg
        if alert_type and not alert_types:
            alert_types = [alert_type]

        serialized = InstanceSerializer.serialize(instance)
        geo_context = GeoContextAnalyzer.detect(serialized)
        plant_id = (
            getattr(instance, "treatment_plant_id", None)
            or getattr(getattr(instance, "analysis", None), "treatment_plant_id", None)
            or getattr(getattr(instance, "treatment_plant", None), "pk", None)
        )
        if plant_id:
            geo_context["plant_id"] = str(plant_id)

        alerts = AlertConfig.objects.filter(active=True)
        if alert_types:
            alerts = alerts.filter(alert_type__in=alert_types)

        triggered_alerts = []

        for alert in alerts:
            try:
                # Evaluate filter conditions safely
                if not SafeConditionEvaluator.evaluate(alert.filter_conditions, serialized):
                    continue

                # AI-priority prediction & update
                predicted_priority = AIAlertPriorityPredictor.predict(serialized)
                if predicted_priority != alert.priority:
                    alert.priority = predicted_priority
                    alert.save(update_fields=['priority'])

                # Format messages safely
                try:
                    subject = alert.template.subject_template.format(**serialized)
                except Exception:
                    subject = alert.template.subject_template or f"Alert: {alert.alert_type}"

                try:
                    body = alert.template.body_template.format(**serialized)
                except Exception:
                    body = alert.template.body_template or str(instance)

                recipients = list(alert.recipients.all())

                # Record alert state first so voice alert can link to it
                state = AlertState.objects.create(
                    alert_config=alert,
                    instance_ref=str(instance),
                    state=AlertState.StateChoices.QUEUED,
                    geo_context=geo_context,
                )

                # Generate persistent voice alert with audio file URL
                voice_url = None
                try:
                    from .models import VoiceAlert
                    voice_alert = VoiceAlert.generate_persistent_voice_alert(
                        message=body,
                        title=subject,
                        alert_config=alert,
                        alert_state=state,
                    )
                    if voice_alert and voice_alert.audio_file:
                        voice_url = voice_alert.audio_file.url
                except Exception as v_err:
                    logger.warning(f"[AlertEngine] Voice alert generation notice: {v_err}")

                # Async dispatch (email, SMS, etc.)
                dispatch_alerts.delay(subject, body, recipients)
                send_websocket_notification.delay(body, group='alerts_stream', title=subject, voice_url=voice_url)

                # Record audit log
                AlertLog.objects.create(
                    alert=alert,
                    content_object=instance,
                    details={
                        'recipients': [u.id for u in recipients],
                        'body': body,
                        'subject': subject,
                        'notes': audit_notes or '',
                    },
                )

                alert.last_triggered = timezone.now()
                alert.save(update_fields=['last_triggered'])
                triggered_alerts.append(state)

                # Real-time push via channels directly to active dashboard streams
                try:
                    channel_layer = get_channel_layer()
                    if channel_layer:
                        ws_payload = {
                            'type': 'alert.message',
                            'title': subject,
                            'message': body,
                            'voice_url': voice_url,
                            'priority': alert.priority,
                            'alert_type': alert.alert_type,
                            'instance_ref': str(getattr(instance, 'id', instance)),
                            'timestamp': timezone.now().isoformat(),
                        }
                        async_to_sync(channel_layer.group_send)('alerts_stream', ws_payload)
                        async_to_sync(channel_layer.group_send)('alerts_group', ws_payload)
                        for u in recipients:
                            async_to_sync(channel_layer.group_send)(f'user_{u.id}_alerts', ws_payload)
                except Exception as ws_err:
                    logger.warning(f"[AlertEngine] WebSocket broadcast notice: {ws_err}")

            except Exception as e:
                logger.exception(f"[AlertEngine] Failed triggering alert for {instance}: {e}")

        return triggered_alerts

    @staticmethod
    def auto_escalate_unacknowledged(alert_type=None, instance=None):
        """
        Auto escalate unacknowledged alerts.
        Optional filter by alert_type or instance.
        """
        states = AlertState.objects.filter(
            state__in=[
                AlertState.StateChoices.QUEUED,
                AlertState.StateChoices.SENT,
                AlertState.StateChoices.ESCALATED,
            ]
        )
        if alert_type:
            states = states.filter(alert_config__alert_type=alert_type)
        if instance:
            states = states.filter(instance_ref=str(instance))

        for state in states:
            try:
                escalate_alert.delay(state.alert_config.id, state.id)
                state.alert_config.last_escalation = timezone.now()
                state.alert_config.save(update_fields=['last_escalation'])
                logger.info(f"[AlertEngine] Auto-escalated AlertState {state.id}")
            except Exception as e:
                logger.warning(f"[AlertEngine] Failed escalation for AlertState {state.id}: {e}")

    # ============================================================
    # Convenience triggers for specific app objects
    # ============================================================
    @staticmethod
    def trigger_for_sensor_measurement(measurement):
        """Sensor/Instrument triggers"""
        return AlertEngine.trigger_alert(measurement, alert_types=[
            'sensor_threshold',
            'sensor_health',
        ])

    @staticmethod
    def trigger_for_derived_metric(metric):
        """Derived metric triggers"""
        return AlertEngine.trigger_alert(metric, alert_types=[
            'derived_metric',
            'phase_anomaly',
        ])

    @staticmethod
    def trigger_for_nonconformity(nc):
        """Non-conformity triggers"""
        return AlertEngine.trigger_alert(nc, alert_types=[
            'nc_detected',
            'nc_escalation',
        ])
