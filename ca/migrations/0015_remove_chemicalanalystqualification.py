from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("ca", "0014_chemicalbatch_received_date_required"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ChemicalAnalystQualification",
        ),
    ]
