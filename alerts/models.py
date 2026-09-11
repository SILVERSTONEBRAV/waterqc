#alerts/models.py
import uuid
import logging
from django.db import models
from django.utils import timezone
from django.db.models import JSONField
from django.contrib.postgres.indexes import GinIndex
from django.apps import apps
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from accounts.models import CustomUser
from .utils import (
    TextToSpeechEngine,
    SafeConditionEvaluator,
    InstanceSerializer,
    AIAlertPriorityPredictor,
    GeoContextAnalyzer,
    AIEscalationForecaster,
)

User = CustomUser
logger = logging.getLogger(__name__)


# ============================================================
# 🧠 ALERT TEMPLATE SYSTEM
# ============================================================
class AlertTemplate(models.Model):
    name = models.CharField(max_length=120, unique=True)
    subject_template = models.TextField()
    body_template = models.TextField()
    version = models.IntegerField(default=1)
    active = models.BooleanField(default=True)
    metadata = JSONField(default=dict)
    auto_voice_enabled = models.BooleanField(default=False)

    class Meta:
        unique_together = ('name', 'version')

    def __str__(self):
        return f"{self.name} v{self.version}"


# ============================================================
# ⚙️ ALERT CATEGORY
# ============================================================
class AlertCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.CASCADE, related_name='subcategories'
    )
    ai_cluster_code = models.CharField(max_length=32, blank=True)

    def __str__(self):
        return self.name


# ============================================================
# 🚨 ALERT CONFIG
# ============================================================
class AlertConfig(models.Model):
    class AlertType(models.TextChoices):
        NONCONFORMITY = 'nonconformity', 'Nonconformity'
        SAMPLING_DELAY = 'sampling_delay', 'Sampling Delay'
        ANALYSIS_MISSED = 'analysis_missed', 'Analysis Missed'
        MAINTENANCE_DUE = 'maintenance_due', 'Maintenance Due'
        VERIFICATION_PENDING = 'verification_pending', 'Verification Pending'
        PERFORMANCE_DEVIATION = 'performance_deviation', 'Performance Deviation'

    class PriorityLevel(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        CRITICAL = 'critical', 'Critical'

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    alert_type = models.CharField(max_length=100, choices=AlertType.choices)
    category = models.ForeignKey(AlertCategory, null=True, blank=True, on_delete=models.SET_NULL)
    priority = models.CharField(max_length=20, choices=PriorityLevel.choices, default=PriorityLevel.MEDIUM)
    template = models.ForeignKey(AlertTemplate, on_delete=models.PROTECT)
    recipients = models.ManyToManyField(User, related_name='alert_configs')

    # Customizable targeting fields
    target_sections = models.ManyToManyField("core.Section", blank=True, help_text="Send alert only to users in these sections")
    target_groups = models.ManyToManyField("auth.Group", blank=True, help_text="Send alert only to users in these groups")
    target_treatment_plants = models.ManyToManyField("t.TreatmentPlant", blank=True, help_text="Send alert only to users linked to these treatment plants")
    allow_ai_recipients = models.BooleanField(default=True, help_text="Include AI-prioritized recipients")

    # Alert timing & escalation
    verify_timeout = models.DurationField()
    verify_before_subsequent = models.DurationField()
    approve_timeout = models.DurationField(default=timezone.timedelta(minutes=30))
    tat_for_escalation = models.DurationField(default=timezone.timedelta(hours=1))
    escalation_timeout = models.DurationField(default=timezone.timedelta(hours=2))
    escalate_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='escalated_alerts')

    filter_conditions = JSONField(default=dict)
    trigger_action = JSONField(default=dict)
    escalation_policy = JSONField(default=dict)
    adaptive_retry_policy = JSONField(default=dict)
    ai_recommended_recipients = JSONField(default=list, blank=True)

    custom_fields = JSONField(default=dict)
    active = models.BooleanField(default=True)
    retry_count = models.PositiveIntegerField(default=0)

    last_triggered = models.DateTimeField(null=True, blank=True)
    last_escalation = models.DateTimeField(null=True, blank=True)
    geo_context = JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    activated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='activated_alerts')

    class Meta:
        indexes = [
            GinIndex(fields=['filter_conditions']),
            GinIndex(fields=['trigger_action']),
            GinIndex(fields=['custom_fields']),
        ]

    def __str__(self):
        return f"{self.alert_type} [{self.priority}]"

    def clean(self):
        SafeConditionEvaluator.validate_structure(self.filter_conditions, 'filter_conditions')
        SafeConditionEvaluator.validate_structure(self.trigger_action, 'trigger_action')

    # ============================================================
    # ✅ FULL ALERT LIFECYCLE
    # ============================================================
    def send_alert(self, instance):
        """
        Full end-to-end alert dispatch for ANY alert type:
        1. Serialize instance & predict AI priority
        2. Evaluate filter conditions
        3. Render template (subject/body)
        4. Resolve dynamic recipients (sections, groups, plants, AI)
        5. Deduplicate contacts & respect per-user preferences
        6. Dispatch via all allowed channels
        7. Voice notifications & WebSocket
        8. Record AlertState
        9. Auto-escalate unacknowledged alerts
        """
        from .tasks import dispatch_alerts, generate_voice_notification, send_websocket_notification
        from accounts.utils import get_contacts_for_alert
        from django.utils import timezone
        from django.apps import apps

        AlertState = apps.get_model('alerts', 'AlertState')
        UserAlertPreference = apps.get_model('alerts', 'UserAlertPreference')

        try:
            # -----------------------------
            # Serialize instance & AI prediction
            # -----------------------------
            serialized = InstanceSerializer.serialize(instance)
            predicted_priority = AIAlertPriorityPredictor.predict(serialized)
            geo_context = GeoContextAnalyzer.detect(serialized)

            if predicted_priority != self.priority:
                self.priority = predicted_priority
                self.save(update_fields=['priority'])

            # -----------------------------
            # Evaluate filter conditions
            # -----------------------------
            if not SafeConditionEvaluator.evaluate(self.filter_conditions, serialized):
                logger.info(f"[alert] Filter conditions not met for {self.alert_type}")
                return

            # -----------------------------
            # Render templates
            # -----------------------------
            subject = self.template.subject_template.format(**serialized)
            body = self.template.body_template.format(**serialized)

            # -----------------------------
            # Collect recipients dynamically
            # -----------------------------
            explicit_user_ids = list(self.recipients.values_list('id', flat=True))
            ai_user_ids = self.ai_recommended_recipients if self.allow_ai_recipients else []

            section_ids = list(self.target_sections.values_list('id', flat=True)) if self.target_sections.exists() else None
            group_ids = list(self.target_groups.values_list('id', flat=True)) if self.target_groups.exists() else None
            plant_ids = list(self.target_treatment_plants.values_list('id', flat=True)) if self.target_treatment_plants.exists() else None

            contacts = get_contacts_for_alert(
                user_ids=explicit_user_ids + ai_user_ids,
                sections=section_ids,
                groups=group_ids,
                treatment_plants=plant_ids
            )

            # -----------------------------
            # Deduplicate & apply user preferences
            # -----------------------------
            seen_keys = set()
            final_contacts = []
            for c in contacts:
                user_id = c.get('id')
                prefs = UserAlertPreference.objects.filter(user_id=user_id).first()
                if prefs:
                    allowed_channels = []
                    if prefs.receive_email and c.get('email'): allowed_channels.append('email')
                    if prefs.receive_sms and c.get('mobile_number'): allowed_channels.append('sms')
                    if prefs.receive_whatsapp and c.get('whatsapp_number'): allowed_channels.append('whatsapp')
                    if prefs.receive_push: allowed_channels.append('push')
                    if prefs.receive_slack and c.get('slack_channel'): allowed_channels.append('slack')
                    if not allowed_channels:
                        continue
                    c['channels'] = allowed_channels

                key = c.get('email') or c.get('mobile_number') or user_id
                if key and key not in seen_keys:
                    final_contacts.append(c)
                    seen_keys.add(key)

            if not final_contacts:
                logger.warning(f"[alert] No recipients resolved for alert {self.alert_type}")
                return

            # -----------------------------
            # Dispatch alerts
            # -----------------------------
            dispatch_alerts.delay(subject, body, final_contacts)

            if getattr(self.template, "auto_voice_enabled", False):
                generate_voice_notification.delay(body)

            ws_group = f"plant_{getattr(instance, 'assigned_treatment_plant', 'general')}_alerts"
            send_websocket_notification.delay(body, group=ws_group)

            # -----------------------------
            # Record AlertState
            # -----------------------------
            AlertState.objects.create(
                alert_config=self,
                instance_ref=str(getattr(instance, "id", instance)),
                state=AlertState.StateChoices.QUEUED,
                geo_context=geo_context,
            )

            self.last_triggered = timezone.now()
            self.save(update_fields=["last_triggered"])
            logger.info(f"[alert] Alert '{self.alert_type}' sent to {len(final_contacts)} recipients")

            # -----------------------------
            # Auto-escalation
            # -----------------------------
            self.auto_escalate_if_unacknowledged()

        except Exception as e:
            logger.exception(f"[alert] Failed to send alert '{self.alert_type}': {e}")

    # ============================================================
    # ✅ GENERIC AUTO-ESCALATION
    # ============================================================
    def auto_escalate_if_unacknowledged(self):
        """
        Generic escalation for ANY alert type:
        - Pending alerts: queued, sent, escalated
        - Sends escalation to 'escalate_to' or AI-prioritized recipients
        - Respects per-user alert preferences
        """
        from .tasks import escalate_alert
        from accounts.utils import get_contacts_for_alert
        from django.apps import apps
        from django.utils import timezone
        from django.contrib.contenttypes.models import ContentType

        AlertState = apps.get_model('alerts', 'AlertState')
        UserAlertPreference = apps.get_model('alerts', 'UserAlertPreference')

        try:
            if self.last_escalation and timezone.now() - self.last_escalation <= self.escalation_timeout:
                return

            pending_states = AlertState.objects.filter(
                alert_config=self,
                state__in=[
                    AlertState.StateChoices.QUEUED,
                    AlertState.StateChoices.SENT,
                    AlertState.StateChoices.ESCALATED
                ]
            )

            for state in pending_states:
                # Determine escalation recipients
                escalate_user_ids = []
                if self.escalate_to:
                    escalate_user_ids.append(self.escalate_to.id)
                if self.ai_recommended_recipients and self.allow_ai_recipients:
                    escalate_user_ids += self.ai_recommended_recipients

                contacts = get_contacts_for_alert(user_ids=escalate_user_ids)
                final_contacts = []
                seen_keys = set()

                for c in contacts:
                    prefs = UserAlertPreference.objects.filter(user_id=c['id']).first()
                    if prefs:
                        allowed_channels = []
                        if prefs.receive_email and c.get('email'): allowed_channels.append('email')
                        if prefs.receive_sms and c.get('mobile_number'): allowed_channels.append('sms')
                        if prefs.receive_whatsapp and c.get('whatsapp_number'): allowed_channels.append('whatsapp')
                        if prefs.receive_push: allowed_channels.append('push')
                        if prefs.receive_slack and c.get('slack_channel'): allowed_channels.append('slack')
                        if not allowed_channels:
                            continue
                        c['channels'] = allowed_channels

                    key = c.get('email') or c.get('mobile_number') or c.get('id')
                    if key and key not in seen_keys:
                        final_contacts.append(c)
                        seen_keys.add(key)

                if final_contacts:
                    # Trigger generic escalation task
                    escalate_alert.delay(self.id, getattr(state, 'instance_ref', None))

            self.last_escalation = timezone.now()
            self.save(update_fields=["last_escalation"])

        except Exception as e:
            logger.exception(f"[alert] Failed auto-escalation for '{self.alert_type}': {e}")


# ============================================================
# 🔁 ALERT STATE
# ============================================================
class AlertState(models.Model):
    class StateChoices(models.TextChoices):
        QUEUED = 'queued'
        SENT = 'sent'
        ESCALATED = 'escalated'
        ACKNOWLEDGED = 'acknowledged'
        VERIFIED = 'verified'
        CLOSED = 'closed'

    alert_config = models.ForeignKey(AlertConfig, on_delete=models.CASCADE)
    instance_ref = models.CharField(max_length=255)
    state = models.CharField(max_length=20, choices=StateChoices.choices, default=StateChoices.QUEUED)
    geo_context = JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.alert_config.alert_type} → {self.state}"


# ============================================================
# ✅ ACKNOWLEDGMENT
# ============================================================
class AlarmAcknowledgment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    acknowledged = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    sentiment_score = models.FloatField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'content_type', 'object_id')


# ============================================================
# 🧩 ALERT LOGS
# ============================================================
class AlertLog(models.Model):
    alert = models.ForeignKey(AlertConfig, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    details = JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)


# ============================================================
# 🔔 LIVE STATE PUSH
# ============================================================
@receiver(post_save, sender=AlertState)
def alert_state_change_observer(sender, instance, **kwargs):
    async_to_sync(get_channel_layer().group_send)(
        "alerts_stream",
        {
            "type": "alert_state",
            "message": f"State changed to {instance.state}",
            "geo": instance.geo_context,
        },
    )


# ============================================================
# 🧠 USER PREFERENCES
# ============================================================
class UserAlertPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="alert_preferences")
    receive_email = models.BooleanField(default=True)
    receive_sms = models.BooleanField(default=False)
    receive_push = models.BooleanField(default=True)
    receive_whatsapp = models.BooleanField(default=False)
    receive_slack = models.BooleanField(default=False)

    preferred_time_window_start = models.TimeField(null=True, blank=True)
    preferred_time_window_end = models.TimeField(null=True, blank=True)
    geo_zone = models.CharField(max_length=120, blank=True)
