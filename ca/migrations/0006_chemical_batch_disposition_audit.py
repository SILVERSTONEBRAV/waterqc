from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("ca", "0005_move_location_to_chemical_batch"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="chemicalbatch",
            name="quantity_utilized",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=16, null=True),
        ),
        migrations.AddField(
            model_name="chemicalbatch",
            name="utilization_remarks",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="chemicalbatch",
            name="utilized_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chemicalbatch",
            name="utilized_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="utilized_chemical_batches", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="chemicalbatch",
            name="quantity_returned",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=16, null=True),
        ),
        migrations.AddField(
            model_name="chemicalbatch",
            name="return_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="chemicalbatch",
            name="returned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chemicalbatch",
            name="returned_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="returned_chemical_batches", to=settings.AUTH_USER_MODEL),
        ),
    ]
