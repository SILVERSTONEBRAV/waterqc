import hashlib
import json

from django.db import migrations, models
from django.db.models import Q


def refresh_formula_hashes(apps, schema_editor):
    Method = apps.get_model("analysis_methods", "ChemicalAnalysisMethod")
    database = schema_editor.connection.alias
    updates = []
    for method in Method.objects.using(database).all().iterator(chunk_size=1000):
        payload = json.dumps(
            {
                "method": method.method,
                "reference": method.kebs_reference,
                "formula": method.formula,
                "inputs": method.inputs_structure,
                "unit": method.unit,
                "precision": method.rounding_precision,
                "rounding_mode": method.rounding_mode,
                "version": method.version,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        method.formula_hash = hashlib.sha256(payload.encode()).hexdigest()
        updates.append(method)
        if len(updates) >= 1000:
            Method.objects.using(database).bulk_update(updates, ["formula_hash"], batch_size=1000)
            updates.clear()
    if updates:
        Method.objects.using(database).bulk_update(updates, ["formula_hash"], batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("analysis_methods", "0002_alter_chemicalanalysismethod_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="chemicalanalysismethod",
            name="rounding_mode",
            field=models.CharField(
                choices=[
                    ("HALF_UP", "Half up"),
                    ("HALF_EVEN", "Half even"),
                    ("DOWN", "Toward zero"),
                    ("UP", "Away from zero"),
                ],
                default="HALF_UP",
                max_length=16,
            ),
        ),
        migrations.RunPython(refresh_formula_hashes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="chemicalanalysismethod",
            constraint=models.CheckConstraint(
                condition=Q(rounding_precision__gte=0, rounding_precision__lte=12),
                name="am_rounding_precision_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="chemicalanalysismethod",
            constraint=models.CheckConstraint(
                condition=Q(rounding_mode__in=["HALF_UP", "HALF_EVEN", "DOWN", "UP"]),
                name="am_rounding_mode_valid",
            ),
        ),
    ]
