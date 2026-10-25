from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def copy_request_locations_to_batches(apps, schema_editor):
    AnalysisRequest = apps.get_model("ca", "ChemicalAnalysisRequest")
    ChemicalBatch = apps.get_model("ca", "ChemicalBatch")
    database = schema_editor.connection.alias

    for request in AnalysisRequest.objects.using(database).exclude(
        batch_id__isnull=True
    ).exclude(location_id__isnull=True).iterator():
        ChemicalBatch.objects.using(database).filter(
            pk=request.batch_id,
            location__isnull=True,
        ).update(location_id=request.location_id)


def copy_batch_locations_to_requests(apps, schema_editor):
    AnalysisRequest = apps.get_model("ca", "ChemicalAnalysisRequest")
    database = schema_editor.connection.alias

    for request in AnalysisRequest.objects.using(database).select_related(
        "batch"
    ).exclude(batch_id__isnull=True).iterator():
        if request.batch_id and request.batch.location_id:
            AnalysisRequest.objects.using(database).filter(
                pk=request.pk,
                location__isnull=True,
            ).update(location_id=request.batch.location_id)


class Migration(migrations.Migration):
    dependencies = [
        ("ca", "0004_remove_systematicrandomsample_unique_sampling_package_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="chemicalbatch",
            name="location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="chemical_batches",
                to="ca.chemicallocation",
            ),
        ),
        migrations.AlterField(
            model_name="chemicalbatch",
            name="received_date",
            field=models.DateField(
                blank=True,
                default=django.utils.timezone.localdate,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="chemicalanalysisrequest",
            name="location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="analysis_requests",
                to="ca.chemicallocation",
            ),
        ),
        migrations.RunPython(
            copy_request_locations_to_batches,
            copy_batch_locations_to_requests,
        ),
        migrations.RemoveField(
            model_name="chemicalanalysisrequest",
            name="location",
        ),
    ]
