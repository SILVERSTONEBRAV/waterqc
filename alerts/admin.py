# alerts/admin.py
import os
from django.contrib import admin
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from .models import (
    VoiceOver,
    VoiceAlert,
    AlertTemplate,
    AlertCategory,
    AlertConfig,
    AlertState,
    AlertNotification,
    AlertLog,
    UserAlertPreference,
)


def get_audio_mime_types(file_field):
    """Return list of appropriate MIME types for the audio element source tags."""
    if not file_field or not getattr(file_field, "name", None):
        return ["audio/mpeg"]
    ext = os.path.splitext(file_field.name.lower())[1]
    if ext in [".m4a", ".mp4"]:
        return ["audio/mp4", "audio/x-m4a", "audio/aac"]
    elif ext == ".wav":
        return ["audio/wav", "audio/x-wav"]
    elif ext == ".ogg":
        return ["audio/ogg"]
    elif ext == ".aac":
        return ["audio/aac"]
    return ["audio/mpeg"]


@admin.register(VoiceOver)
class VoiceOverAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user_display",
        "gender",
        "accent_profile",
        "slot",
        "usage_count",
        "is_active",
        "last_voiced_at",
        "audio_sample_preview",
    )
    list_filter = ("is_active", "gender", "accent_profile", "slot")
    search_fields = (
        "name",
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )
    readonly_fields = (
        "usage_count",
        "last_voiced_at",
        "created_at",
        "updated_at",
        "audio_sample_preview",
    )
    actions = ["generate_test_alerts"]
    fieldsets = (
        ("Profile & User", {
            "fields": ("name", "user", "is_active", "slot"),
            "description": "Voice clip must belong to a registered user from the accounts app. Maximum of two voices allowed in the system.",
        }),
        ("Sample Voice Clip", {
            "fields": ("sample_clip", "audio_sample_preview"),
            "description": "Upload a voice clip sample of the user to be used as voice over.",
        }),
        ("Acoustic & Synthesis Settings", {
            "fields": ("gender", "accent_profile", "speech_rate"),
            "description": "Acoustic and synthesis parameters for generating custom alert messages.",
        }),
        ("Usage & Tracking", {
            "fields": ("usage_count", "last_voiced_at", "created_at", "updated_at"),
            "description": "Usage counter guaranteeing strict 1:1 fair alternation with the other voice.",
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:object_id>/test-voice/",
                self.admin_site.admin_view(self.test_voice_view),
                name="alerts_voiceover_test_voice",
            ),
        ]
        return custom_urls + urls

    def user_display(self, obj):
        full_name = getattr(obj.user, "full_name", None) or obj.user.get_username()
        return f"{full_name} ({obj.user.get_username()})"
    user_display.short_description = "Accounts User"

    def audio_sample_preview(self, obj):
        if obj.sample_clip:
            url = obj.sample_clip.url
            mime_types = get_audio_mime_types(obj.sample_clip)
            sources_html = "".join([f'<source src="{url}" type="{m}">' for m in mime_types])
            sources_html += f'<source src="{url}">'
            test_url = reverse("admin:alerts_voiceover_test_voice", args=[obj.pk])

            return format_html(
                '<div style="display:inline-flex;align-items:center;gap:6px;flex-wrap:nowrap;">'
                '<audio controls preload="metadata" style="height:30px;width:190px;vertical-align:middle;" src="{}">'
                '{}'
                'Your browser does not support audio element.'
                '</audio>'
                '<a href="{}" target="_blank" download style="display:inline-flex;align-items:center;padding:3px 7px;border-radius:4px;background:#f3f4f6;color:#1f2937;font-size:11px;font-weight:600;text-decoration:none;border:1px solid #d1d5db;" title="Open or download audio file">'
                '&#128266; Open'
                '</a>'
                '<a href="{}" style="display:inline-flex;align-items:center;padding:3px 7px;border-radius:4px;background:#4f46e5;color:#ffffff;font-size:11px;font-weight:600;text-decoration:none;" title="Generate and listen to synthesized speech alert with this voice">'
                '&#127908; Test Speech'
                '</a>'
                '</div>',
                url,
                format_html(sources_html),
                url,
                test_url,
            )
        return "No sample uploaded"
    audio_sample_preview.short_description = "Sample Clip Player & Actions"

    def test_voice_view(self, request, object_id):
        voice = get_object_or_404(VoiceOver, pk=object_id)
        alert = voice.generate_test_alert()
        if alert and alert.audio_file:
            mime_type = get_audio_mime_types(alert.audio_file)[0]
            messages.success(
                request,
                format_html(
                    '<strong>Voice Alert Generated Successfully!</strong> Voiced by <em>{}</em> (reference clone: {}). '
                    '<div style="margin-top:6px;"><audio controls autoplay preload="auto" style="height:32px;vertical-align:middle;">'
                    '<source src="{}" type="{}"><source src="{}">'
                    '</audio> <a href="{}" style="margin-left:8px;font-weight:bold;">View in Voice Alerts &rarr;</a></div>',
                    voice.name,
                    "yes" if alert.voice_cloned else "no",
                    alert.audio_file.url,
                    mime_type,
                    alert.audio_file.url,
                    reverse("admin:alerts_voicealert_changelist"),
                )
            )
        else:
            messages.error(request, f"Failed to synthesize voice alert for {voice.name}.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("admin:alerts_voiceover_changelist"))

    @admin.action(description="🎙️ Generate test voice alert for selected voices")
    def generate_test_alerts(self, request, queryset):
        count = 0
        for voice in queryset:
            alert = voice.generate_test_alert()
            if alert:
                count += 1
        messages.success(request, f"Successfully synthesized {count} test voice alert(s). Check Voice Alerts table below.")


@admin.register(VoiceAlert)
class VoiceAlertAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "speaker_display",
        "voice_over",
        "voice_cloned",
        "duration_seconds",
        "repeat_count",
        "repeat_due_at",
        "audio_player",
        "created_at",
    )
    list_filter = ("voice_cloned", "voice_over", "created_at")
    search_fields = (
        "title",
        "message",
        "speaker_user__username",
        "speaker_user__first_name",
        "speaker_user__last_name",
    )
    readonly_fields = (
        "uuid",
        "audio_player",
        "voice_cloned",
        "repeat_due_at",
        "repeat_count",
        "created_at",
    )
    fieldsets = (
        ("Alert Details", {
            "fields": ("uuid", "title", "message", "alert_config", "alert_state"),
        }),
        ("Voice Identity & Playback", {
            "fields": ("voice_over", "speaker_user", "voice_cloned", "audio_file", "audio_player", "duration_seconds"),
        }),
        ("Analytics", {
            "fields": ("is_played", "play_count", "repeat_due_at", "repeat_count", "created_at"),
        }),
    )

    def speaker_display(self, obj):
        if obj.speaker_user:
            return getattr(obj.speaker_user, "full_name", None) or obj.speaker_user.get_username()
        return "System Voice"
    speaker_display.short_description = "Speaker"

    def audio_player(self, obj):
        if obj.audio_file:
            url = obj.audio_file.url
            mime_types = get_audio_mime_types(obj.audio_file)
            sources_html = "".join([f'<source src="{url}" type="{m}">' for m in mime_types])
            sources_html += f'<source src="{url}">'
            return format_html(
                '<div style="display:inline-flex;align-items:center;gap:6px;">'
                '<audio controls preload="metadata" style="height:32px;width:220px;vertical-align:middle;" src="{}">'
                '{}'
                'Your browser does not support audio element.'
                '</audio>'
                '<a href="{}" target="_blank" download style="display:inline-flex;align-items:center;padding:3px 7px;border-radius:4px;background:#f3f4f6;color:#1f2937;font-size:11px;font-weight:600;text-decoration:none;border:1px solid #d1d5db;" title="Open or download audio file">'
                '&#128266; Open'
                '</a>'
                '</div>',
                url,
                format_html(sources_html),
                url,
            )
        return "No audio generated"
    audio_player.short_description = "Voice Alert Audio"


@admin.register(AlertTemplate)
class AlertTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "active", "auto_voice_enabled")
    list_filter = ("active", "auto_voice_enabled")
    search_fields = ("name", "subject_template", "body_template")


@admin.register(AlertCategory)
class AlertCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "ai_cluster_code")
    search_fields = ("name", "ai_cluster_code")


@admin.register(AlertConfig)
class AlertConfigAdmin(admin.ModelAdmin):
    list_display = (
        "alert_type",
        "priority",
        "voice_persistence_mode",
        "voice_repeat_interval_seconds",
        "voice_repeat_max_count",
        "active",
        "last_triggered",
    )
    list_filter = ("alert_type", "priority", "voice_persistence_mode", "active")
    search_fields = ("alert_type",)
    filter_horizontal = ("recipients", "target_sections", "target_groups", "target_treatment_plants")


@admin.register(AlertState)
class AlertStateAdmin(admin.ModelAdmin):
    list_display = (
        "alert_config", "instance_ref", "priority", "state", "escalation_count",
        "repeat_count", "repeat_due_at", "escalation_due_at", "updated_at",
    )
    list_filter = ("state",)
    search_fields = ("instance_ref",)
    readonly_fields = ("repeat_due_at", "repeat_count", "created_at", "updated_at")


@admin.register(AlertNotification)
class AlertNotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "alert_state", "sequence", "delivery_status", "attempts", "delivered_at", "acknowledged_at")
    list_filter = ("delivery_status", "is_escalation", "priority", "created_at")
    search_fields = ("title", "message", "recipient__username", "recipient__email", "alert_state__instance_ref")
    readonly_fields = ("created_at", "updated_at", "last_attempt_at", "delivered_at", "delivery_results")
    raw_id_fields = ("alert_state", "recipient")


@admin.register(AlertLog)
class AlertLogAdmin(admin.ModelAdmin):
    list_display = ("alert", "content_type", "object_id", "timestamp")
    list_filter = ("timestamp",)


@admin.register(UserAlertPreference)
class UserAlertPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "receive_email", "receive_sms", "receive_push", "receive_whatsapp", "receive_slack")
    list_filter = ("receive_email", "receive_sms", "receive_push", "receive_whatsapp", "receive_slack")
    search_fields = ("user__username", "user__email")
