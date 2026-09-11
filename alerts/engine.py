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
    def trigger_alert(instance, alert_types=None, audit_notes=None):
        """
        Trigger alerts relevant to an instance.
        - `alert_types`: list of alert_type strings to filter alerts
        - `audit_notes`: optional notes for logs
        """
        serialized = InstanceSerializer.serialize(instance)
        geo_context = GeoContextAnalyzer.detect(serialized)

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

                # Format messages
                subject = alert.template.subject_template.format(**serialized)
                body = alert.template.body_template.format(**serialized)
                recipients = list(alert.recipients.all())

                # Async dispatch
                dispatch_alerts.delay(subject, body, [u.id for u in recipients])
                if alert.template.auto_voice_enabled:
                    generate_voice_notification.delay(body)
                send_websocket_notification.delay(body, group='alerts_stream')

                # Record alert state
                state = AlertState.objects.create(
                    alert_config=alert,
                    instance_ref=str(instance),
                    state=AlertState.StateChoices.QUEUED,
                    geo_context=geo_context,
                )

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

                # Real-time push via channels
                async_to_sync(get_channel_layer().group_send)(
                    'alerts_stream',
                    {
                        'type': 'alert_state',
                        'message': f"Alert triggered: {alert.alert_type} → {state.state}",
                        'geo': geo_context,
                        'instance': serialized,
                        'priority': alert.priority,
                    },
                )

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
