from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def backfill_ca_voice_reminders(apps, schema_editor):
    ChemicalWorkflowAlert = apps.get_model("ca", "ChemicalWorkflowAlert")
    AlertConfig = apps.get_model("alerts", "AlertConfig")
    VoiceAlert = apps.get_model("alerts", "VoiceAlert")
    database = schema_editor.connection.alias
    now = timezone.now()

    open_alerts = ChemicalWorkflowAlert.objects.using(database).filter(
        acknowledged_at__isnull=True
    ).select_related("analysis_request")
    for alert in open_alerts.iterator(chunk_size=200):
        assignment_alert = alert.alert_type in {
            "ca_assignment_pending",
            "ca_assignment_escalation",
        }
        if (
            assignment_alert
            and alert.analysis_request_id
            and alert.analysis_request.assigned_analysts.using(database).exists()
        ):
            ChemicalWorkflowAlert.objects.using(database).filter(pk=alert.pk).update(
                acknowledged_at=now
            )
            continue

        voice_alert = VoiceAlert.objects.using(database).select_related(
            "alert_config", "alert_config__template"
        ).filter(source_key=f"ca-workflow:{alert.pk}").first()
        if not voice_alert or not voice_alert.audio_file:
            continue
        config = voice_alert.alert_config
        if config is None:
            config = AlertConfig.objects.using(database).select_related("template").filter(
                alert_type=alert.alert_type
            ).first()
        if config:
            mode = config.voice_persistence_mode
            if (
                not config.active
                or not config.template.active
                or not config.template.auto_voice_enabled
                or mode == "once"
                or (config.voice_repeat_max_count and voice_alert.repeat_count >= config.voice_repeat_max_count)
            ):
                continue
            interval = max(5, int(config.voice_repeat_interval_seconds or 60))
        else:
            interval = 60

        VoiceAlert.objects.using(database).filter(pk=voice_alert.pk).update(
            alert_config=config,
            repeat_due_at=now + timedelta(seconds=interval),
        )


class Migration(migrations.Migration):

    dependencies = [
        ("ca", "0019_alum_standardization_calculations"),
        ("alerts", "0006_unbounded_voice_repeat_counts"),
    ]

    operations = [
        migrations.RunPython(backfill_ca_voice_reminders, migrations.RunPython.noop),
    ]
