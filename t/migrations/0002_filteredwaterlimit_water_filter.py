from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("t", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="filteredwaterlimit",
            name="water_filter",
            field=models.ForeignKey(
                blank=True,
                help_text="Filter this parameter limit applies to.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="filtered_water_limits",
                to="t.waterfilter",
            ),
        ),
    ]
