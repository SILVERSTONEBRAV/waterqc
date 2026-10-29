# Generated for configurable voice reminder persistence.

from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def backfill_open_voice_alerts(apps, schema_editor):
    AlertState = apps.get_model("alerts", "AlertState")
    database = schema_editor.connection.alias
    now = timezone.now()
    states = AlertState.objects.using(database).filter(
        state__in=("queued", "sent", "escalated"),
        repeat_due_at__isnull=True,
        alert_config__active=True,
        alert_config__voice_persistence_mode="until_acknowledged",
        alert_config__template__active=True,
        alert_config__template__auto_voice_enabled=True,
    ).select_related("alert_config")
    for state in states.iterator(chunk_size=200):
        has_push_recipient = any(
            "push" in (channels or [])
            for channels in state.notifications.using(database)
            .filter(acknowledged_at__isnull=True)
            .values_list("channels", flat=True)
        )
        if not has_push_recipient:
            continue
        state.repeat_due_at = now + timedelta(
            seconds=max(5, int(state.alert_config.voice_repeat_interval_seconds or 60))
        )
        state.save(using=database, update_fields=["repeat_due_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0004_alertstate_created_at_alertstate_escalation_count_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alertconfig",
            name="alert_type",
            field=models.CharField(
                choices=[
                    ("nonconformity", "Nonconformity"),
                    ("auto_verification", "Automatic Verification"),
                    ("sampling_delay", "Sampling Delay"),
                    ("analysis_missed", "Analysis Missed"),
                    ("maintenance_due", "Maintenance Due"),
                    ("verification_pending", "Verification Pending"),
                    ("performance_deviation", "Performance Deviation"),
                    ("ca_assignment_pending", "CA analyst assignment pending"),
                    ("ca_assignment_escalation", "CA analyst assignment escalation"),
                ],
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="alertconfig",
            name="voice_persistence_mode",
            field=models.CharField(
                choices=[
                    ("once", "Play once"),
                    ("until_acknowledged", "Repeat until acknowledged"),
                    ("until_analyst_assigned", "Repeat until an analyst is assigned"),
                ],
                default="until_acknowledged",
                help_text="Controls how long voiced notifications repeat. The template must also allow auto voice.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="alertconfig",
            name="voice_repeat_interval_seconds",
            field=models.PositiveIntegerField(
                default=60,
                help_text="Seconds between voice reminders. Minimum effective interval is 5 seconds.",
            ),
        ),
        migrations.AddField(
            model_name="alertconfig",
            name="voice_repeat_max_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Maximum repeat count; 0 repeats until the selected completion condition is met.",
            ),
        ),
        migrations.AddField(
            model_name="voicealert",
            name="repeat_due_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="voicealert",
            name="repeat_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(backfill_open_voice_alerts, migrations.RunPython.noop),
    ]
