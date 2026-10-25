from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("filtered_water", "0001_initial"),
        ("t", "0002_filteredwaterlimit_water_filter"),
    ]

    operations = [
        migrations.AlterField(
            model_name="filteredwaterresults",
            name="result_value",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Measured value for this parameter on the specific filter.",
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
