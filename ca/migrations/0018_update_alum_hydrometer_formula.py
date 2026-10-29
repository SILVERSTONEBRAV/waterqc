# Generated manually for Alum hydrometer formula update
from django.db import migrations


def update_alum_hydrometer_formula(apps, schema_editor):
    Chemical = apps.get_model("ca", "Chemical")
    Chemical.objects.filter(
        name__icontains="Aluminium Sulphate"
    ).update(hydrometer_formula="(reading + 0.48) / 0.746")
    Chemical.objects.filter(
        code__iexact="ALUM"
    ).update(hydrometer_formula="(reading + 0.48) / 0.746")


def reverse_alum_hydrometer_formula(apps, schema_editor):
    Chemical = apps.get_model("ca", "Chemical")
    Chemical.objects.filter(
        name__icontains="Aluminium Sulphate"
    ).update(hydrometer_formula="")


class Migration(migrations.Migration):

    dependencies = [
        ("ca", "0017_alter_batchtestresult_analyst"),
    ]

    operations = [
        migrations.RunPython(
            update_alum_hydrometer_formula,
            reverse_code=reverse_alum_hydrometer_formula,
        ),
    ]
