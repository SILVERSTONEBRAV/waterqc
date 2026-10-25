from django.db import migrations, models


def classify_legacy_placeholders(apps, schema_editor):
    Result = apps.get_model("microbial", "MicrobialParameterResult")
    Result.objects.filter(manually_editable=True, value=0.0).update(
        entry_status="legacy_unverified"
    )


class Migration(migrations.Migration):
    dependencies = [("microbial", "0002_initial")]

    operations = [
        migrations.AddField(
            model_name="microbialparameterresult",
            name="entry_status",
            field=models.CharField(
                choices=[
                    ("recorded", "Recorded"),
                    ("pending", "Pending entry"),
                    ("legacy_unverified", "Verify historical value"),
                ],
                db_index=True,
                default="recorded",
                max_length=24,
            ),
        ),
        migrations.RunPython(classify_legacy_placeholders, migrations.RunPython.noop),
    ]
