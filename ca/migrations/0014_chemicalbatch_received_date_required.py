from django.db import migrations, models
import django.utils.timezone


def populate_missing_received_dates(apps, schema_editor):
    ChemicalBatch = apps.get_model("ca", "ChemicalBatch")
    database = schema_editor.connection.alias
    ChemicalBatch.objects.using(database).filter(
        received_date__isnull=True,
    ).update(received_date=django.utils.timezone.localdate())


class Migration(migrations.Migration):
    dependencies = [
        ("ca", "0013_chemicalanalysisprocess_retest_parameter_and_more"),
    ]

    operations = [
        migrations.RunPython(
            populate_missing_received_dates,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="chemicalbatch",
            name="received_date",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
    ]
