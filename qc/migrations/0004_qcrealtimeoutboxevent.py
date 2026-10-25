import uuid

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("qc", "0003_alter_clarifiedwaterresult_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="QCRealtimeOutboxEvent",
            fields=[
                (
                    "event_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("event_type", models.CharField(db_index=True, max_length=80)),
                ("aggregate_type", models.CharField(max_length=80)),
                ("aggregate_id", models.CharField(max_length=80)),
                ("plant_id", models.PositiveBigIntegerField(db_index=True)),
                ("payload", models.JSONField(default=dict)),
                (
                    "created_at",
                    models.DateTimeField(
                        db_index=True,
                        default=django.utils.timezone.now,
                    ),
                ),
                (
                    "available_at",
                    models.DateTimeField(
                        db_index=True,
                        default=django.utils.timezone.now,
                    ),
                ),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
            ],
            options={
                "ordering": ("created_at", "event_id"),
                "indexes": [
                    models.Index(
                        fields=["delivered_at", "available_at"],
                        name="qc_outbox_pending_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(attempt_count__gte=0),
                        name="qc_outbox_attempts_nonneg",
                    ),
                ],
            },
        ),
    ]
