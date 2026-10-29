from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("qc", "0004_qcrealtimeoutboxevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="samplingschedule",
            name="adaptive",
            field=models.BooleanField(
                default=False,
                help_text="Whether this schedule dynamically adapts to operational alerts.",
            ),
        ),
        migrations.AddField(
            model_name="samplingschedule",
            name="last_auto_update",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="samplingschedule",
            name="adaptive_confidence",
            field=models.FloatField(
                default=0.0,
                help_text="Confidence score for adaptive interval decisions.",
            ),
        ),
    ]
