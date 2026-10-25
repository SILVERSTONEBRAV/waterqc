import io
import os
import uuid
import logging
from typing import Optional
from django.db import models
from django.utils import timezone
from django.db.models import JSONField, F
from django.contrib.postgres.indexes import GinIndex
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
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
    auto_voice_enabled = models.BooleanField(default=True)

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

            # -----------------------------
            # Record AlertState
            # -----------------------------
            alert_state = AlertState.objects.create(
                alert_config=self,
                instance_ref=str(getattr(instance, "id", instance)),
                state=AlertState.StateChoices.QUEUED,
                geo_context=geo_context,
            )

            # -----------------------------
            # Persistent Voice Alert (Fair 1:1 Alternation)
            # -----------------------------
            try:
                VoiceAlert.generate_persistent_voice_alert(
                    message=body,
                    title=subject,
                    alert_config=self,
                    alert_state=alert_state,
                )
            except Exception as voice_err:
                logger.warning(f"[alert] Voice alert generation exception: {voice_err}")

            # Every notification and alert generates a corresponding voice message
            generate_voice_notification.delay(body, alert_config_id=self.id, title=subject)

            ws_group = f"plant_{getattr(instance, 'assigned_treatment_plant', 'general')}_alerts"
            send_websocket_notification.delay(body, group=ws_group)

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
def alert_state_change_observer(sender, instance, created=False, **kwargs):
    """Publish state changes only to the alert rule's explicit recipients."""
    if created:
        # The alert dispatch path sends the initial event to each recipient.
        return
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        recipient_ids = instance.alert_config.recipients.values_list("pk", flat=True)
        message = {
            "type": "alert_state",
            "message": f"State changed to {instance.state}",
            "timestamp": timezone.now().isoformat(),
        }
        for user_id in recipient_ids.iterator():
            async_to_sync(channel_layer.group_send)(f"user_{user_id}_alerts", message)
    except Exception:
        logger.exception("Could not publish alert state update to its recipients")


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


# ============================================================
# 🎙️ VOICE SYNTHESIS HELPER
# ============================================================
def synthesize_alert_audio(message: str, accent: str = "co.uk", speech_rate: float = 1.0) -> bytes:
    """
    Synthesize audio speech bytes for custom alert message text.
    Uses gTTS with voice accent profile, with offline pyttsx3 fallback.
    """
    try:
        from gtts import gTTS
        fp = io.BytesIO()
        tts = gTTS(text=message, lang="en", tld=accent or "co.uk")
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.read()
    except Exception as exc:
        logger.warning(f"[VoiceAlert] gTTS synthesis failed ({exc}); falling back to offline TTS...")
        try:
            import tempfile
            import pyttsx3
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            engine = pyttsx3.init()
            if speech_rate and speech_rate != 1.0:
                engine.setProperty("rate", int(200 * speech_rate))
            engine.save_to_file(message, tmp_path)
            engine.runAndWait()
            with open(tmp_path, "rb") as f:
                data = f.read()
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return data
        except Exception as fallback_err:
            logger.error(f"[VoiceAlert] Offline TTS fallback failed: {fallback_err}")
            return b""


def optimize_m4a_faststart(file_path: str):
    """
    Rearrange MP4/M4A atoms so that 'moov' atom precedes 'mdat'.
    Enables instant web streaming and immediate browser playback without buffering delays.
    """
    import struct
    import shutil
    try:
        if not os.path.exists(file_path):
            return
        with open(file_path, "rb") as f:
            data = f.read()
        idx = 0
        atoms = []
        while idx < len(data):
            if idx + 8 > len(data):
                break
            size = struct.unpack(">I", data[idx:idx + 4])[0]
            name = data[idx + 4:idx + 8].decode("latin1", errors="ignore")
            if size == 1:
                size = struct.unpack(">Q", data[idx + 8:idx + 16])[0]
            elif size == 0:
                size = len(data) - idx
            atoms.append((name, idx, size))
            idx += size

        moov_atom = [a for a in atoms if a[0] == "moov"]
        mdat_atom = [a for a in atoms if a[0] == "mdat"]
        if not moov_atom or not mdat_atom:
            return
        moov, mdat = moov_atom[0], mdat_atom[0]
        if moov[1] < mdat[1]:
            return  # Already faststarted

        moov_data = bytearray(data[moov[1]:moov[1] + moov[2]])
        moov_len = len(moov_data)

        stco_idx = 0
        while True:
            pos = moov_data.find(b"stco", stco_idx)
            if pos == -1:
                break
            entry_count = struct.unpack(">I", moov_data[pos + 8:pos + 12])[0]
            for i in range(entry_count):
                e_pos = pos + 12 + (i * 4)
                old_offset = struct.unpack(">I", moov_data[e_pos:e_pos + 4])[0]
                moov_data[e_pos:e_pos + 4] = struct.pack(">I", old_offset + moov_len)
            stco_idx = pos + 4

        pre_mdat = b""
        for a in atoms:
            if a[0] not in ("moov", "mdat"):
                pre_mdat += data[a[1]:a[1] + a[2]]
        mdat_data = data[mdat[1]:mdat[1] + mdat[2]]

        temp_path = file_path + ".fast.tmp"
        with open(temp_path, "wb") as f:
            f.write(pre_mdat)
            f.write(moov_data)
            f.write(mdat_data)
        shutil.move(temp_path, file_path)
        logger.info(f"[VoiceOver] Successfully faststarted audio file {file_path}")
    except Exception as exc:
        logger.warning(f"[VoiceOver] Faststart optimization error: {exc}")


# ============================================================
# 🎙️ VOICE OVER MODEL (MAXIMUM OF TWO VOICES)
# ============================================================
class VoiceOver(models.Model):
    """
    Voice Over model storing sample voice clips of users from the accounts app.
    Enforces a maximum of two voices.
    Provides 1:1 interchangeable fair distribution for all generated alert notifications.
    """
    class VoiceGender(models.TextChoices):
        FEMALE = "female", "Female Voice"
        MALE = "male", "Male Voice"
        NEUTRAL = "neutral", "Neutral Voice"

    class AccentProfile(models.TextChoices):
        BRITISH = "co.uk", "British English (co.uk)"
        AMERICAN = "com", "US English (com)"
        AUSTRALIAN = "com.au", "Australian English (com.au)"
        CANADIAN = "ca", "Canadian English (ca)"
        SOUTH_AFRICAN = "co.za", "African English (co.za)"
        INDIAN = "co.in", "Indian English (co.in)"
        IRISH = "ie", "Irish English (ie)"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="voice_overs",
        help_text="User from the accounts app whose voice is used as voice over."
    )
    name = models.CharField(
        max_length=120,
        help_text="Descriptive title or label for this voice over (e.g. 'Analyst Sarah - Plant A')"
    )
    sample_clip = models.FileField(
        upload_to="voice_overs/samples/",
        help_text="Sample voice audio clip (MP3, WAV, OGG) of the accounts user to be used as voice over."
    )
    gender = models.CharField(
        max_length=20,
        choices=VoiceGender.choices,
        default=VoiceGender.NEUTRAL,
        help_text="Voice gender profile for synthesis alignment."
    )
    accent_profile = models.CharField(
        max_length=30,
        choices=AccentProfile.choices,
        default=AccentProfile.BRITISH,
        help_text="Voice dialect/accent used for voice alert synthesis."
    )
    speech_rate = models.FloatField(
        default=1.0,
        help_text="Speed multiplier for custom alert voicing (0.75 - 1.5)."
    )
    slot = models.PositiveSmallIntegerField(
        choices=[(1, "Voice Slot 1"), (2, "Voice Slot 2")],
        null=True,
        blank=True,
        unique=True,
        help_text="Designated voice slot (Slot 1 or Slot 2; maximum 2 voices)."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this voice is actively used for generating alert messages."
    )
    usage_count = models.PositiveBigIntegerField(
        default=0,
        help_text="Total alert messages voiced by this profile (used to guarantee 1:1 fair ratio)."
    )
    last_voiced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this voice last synthesized an alert."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Voice Over"
        verbose_name_plural = "Voice Overs"
        ordering = ["slot", "id"]

    def __str__(self):
        full_name = getattr(self.user, "full_name", None) or self.user.get_username()
        slot_str = f" [Slot {self.slot}]" if self.slot else ""
        return f"VoiceOver: {self.name} ({full_name}){slot_str} - {self.get_accent_profile_display()}"

    def clean(self):
        super().clean()
        # Verify user belongs to the accounts app
        from accounts.models import CustomUser
        if self.user_id:
            try:
                user_instance = CustomUser.objects.get(pk=self.user_id)
                if not isinstance(user_instance, CustomUser):
                    raise ValidationError({"user": "Voice clip must belong to a user from the accounts app."})
            except CustomUser.DoesNotExist:
                raise ValidationError({"user": "Specified user not found in accounts app."})

        # Enforce maximum of two active voices in the system
        qs = VoiceOver.objects.filter(is_active=True)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if self.is_active and qs.count() >= 2:
            raise ValidationError(
                "A maximum of two voices can be active simultaneously. "
                "Please deactivate or update an existing voice before configuring a new one."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        if self.sample_clip and hasattr(self.sample_clip, 'path') and os.path.exists(self.sample_clip.path):
            name = self.sample_clip.name.lower()
            if name.endswith('.m4a') or name.endswith('.mp4'):
                optimize_m4a_faststart(self.sample_clip.path)

    def generate_test_alert(self, custom_message: Optional[str] = None) -> "VoiceAlert":
        """Generate a persistent test VoiceAlert using this specific voice profile."""
        full_name = getattr(self.user, "full_name", None) or self.user.get_username()
        msg = custom_message or (
            f"Testing voice alert system. This is voice profile {self.name} for user {full_name}. "
            f"All quality control operations are functioning nominally."
        )
        return VoiceAlert.generate_persistent_voice_alert(
            message=msg,
            title=f"Voice Test - {self.name}",
            forced_voice=self,
        )

    @classmethod
    def get_next_voice(cls) -> Optional["VoiceOver"]:
        """
        Fair 1:1 ratio scheduler.
        Interchangeably alternates between the two active voices with exact 50/50 balance.
        Selects the active voice that has been used fewer times (lowest usage_count).
        """
        active_voices = list(cls.objects.filter(is_active=True).order_by("usage_count", "id")[:2])
        if not active_voices:
            return None
        if len(active_voices) == 1:
            return active_voices[0]
        # Return the one with lower usage_count (strict 1:1 ratio)
        return active_voices[0]

    def record_usage(self):
        """Atomically increment usage counter for 1:1 fairness tracking."""
        VoiceOver.objects.filter(pk=self.pk).update(
            usage_count=F("usage_count") + 1,
            last_voiced_at=timezone.now()
        )
        self.refresh_from_db(fields=["usage_count", "last_voiced_at"])


# ============================================================
# 🔊 PERSISTENT VOICE ALERT MODEL
# ============================================================
class VoiceAlert(models.Model):
    """
    Persistent voice alert record accompanying every notification.
    Generated using the configured VoiceOver profiles in a 1:1 interchangeable ratio.
    """
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    voice_over = models.ForeignKey(
        VoiceOver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_voice_alerts",
        help_text="The VoiceOver profile used to voice this alert."
    )
    speaker_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voiced_alerts",
        help_text="The accounts user whose voice identity generated this alert."
    )
    alert_config = models.ForeignKey(
        AlertConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voice_alerts",
        help_text="Associated alert configuration rule."
    )
    alert_state = models.ForeignKey(
        AlertState,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voice_alerts",
        help_text="Associated alert state/dispatch event."
    )
    title = models.CharField(max_length=255, blank=True)
    message = models.TextField(help_text="Full text message voiced in this alert.")
    audio_file = models.FileField(
        upload_to="voice_alerts/notifications/",
        help_text="Persistent audio file of the voiced alert."
    )
    duration_seconds = models.FloatField(default=0.0)
    is_played = models.BooleanField(default=False)
    play_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Voice Alert"
        verbose_name_plural = "Voice Alerts"
        ordering = ["-created_at"]

    def __str__(self):
        speaker = getattr(self.speaker_user, "username", "System Voice")
        return f"VoiceAlert [{speaker}]: {self.title or self.message[:40]}"

    @classmethod
    def generate_persistent_voice_alert(
        cls,
        message: str,
        title: str = "",
        alert_config: Optional[AlertConfig] = None,
        alert_state: Optional[AlertState] = None,
        forced_voice: Optional["VoiceOver"] = None,
    ) -> Optional["VoiceAlert"]:
        """
        Generates and persistently saves a custom voice alert for a notification,
        fairly selecting from the two VoiceOver profiles in a 1:1 ratio.
        """
        voice = forced_voice or VoiceOver.get_next_voice()
        speaker = voice.user if voice else None
        accent = voice.accent_profile if voice else "co.uk"
        rate = voice.speech_rate if voice else 1.0

        # Synthesize audio bytes
        audio_bytes = synthesize_alert_audio(message, accent=accent, speech_rate=rate)
        if not audio_bytes:
            logger.warning("[VoiceAlert] No audio bytes generated for message.")
            return None

        # Build unique filename
        alert_uuid = uuid.uuid4()
        filename = f"voice_alert_{alert_uuid.hex[:12]}.mp3"

        # Create persistent VoiceAlert
        voice_alert = cls(
            uuid=alert_uuid,
            voice_over=voice,
            speaker_user=speaker,
            alert_config=alert_config,
            alert_state=alert_state,
            title=title or (alert_config.alert_type if alert_config else "Alert Notification"),
            message=message,
            duration_seconds=round(max(1.0, len(message.split()) * 0.4), 1),
        )
        voice_alert.audio_file.save(filename, ContentFile(audio_bytes), save=False)
        voice_alert.save()

        # Update voice usage count for 1:1 fair ratio tracking
        if voice:
            voice.record_usage()

        # Broadcast real-time voice alert event over WebSockets (Django Channels)
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                payload = {
                    "type": "voice.alert",
                    "id": str(voice_alert.uuid),
                    "audio_url": voice_alert.audio_file.url,
                    "message": message,
                    "title": voice_alert.title,
                    "speaker": getattr(speaker, "full_name", None) or getattr(speaker, "username", "System Voice"),
                    "timestamp": voice_alert.created_at.isoformat(),
                }
                async_to_sync(channel_layer.group_send)("alerts_group", payload)
                async_to_sync(channel_layer.group_send)("alerts_stream", payload)
                if alert_config:
                    for recipient in alert_config.recipients.iterator():
                        async_to_sync(channel_layer.group_send)(f"user_{recipient.pk}_alerts", payload)
        except Exception as ws_err:
            logger.debug(f"[VoiceAlert] WebSocket broadcast notice: {ws_err}")

        logger.info(f"[VoiceAlert] Created persistent voice alert {voice_alert.uuid} (voice={voice})")
        return voice_alert

