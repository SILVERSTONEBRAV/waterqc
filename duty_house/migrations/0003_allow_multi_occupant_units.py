from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("duty_house", "0002_remove_location_duty_house__parent__b71b81_idx_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="dutyhouseoccupancy",
            name="unique_current_occupancy_per_unit",
        ),
    ]
