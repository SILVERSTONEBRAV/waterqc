import hashlib
import json

from django.db import migrations, models
from django.db.models import Max


METHOD_REFERENCE = "Procedure as configured for aluminium sulphate analysis"


def _method_profile(Method, database, *, title, formula, inputs, unit, description, tags):
    method_name = f"Alum {title} ({unit or 'unit not set'})"
    existing = Method.objects.using(database).filter(method=method_name).order_by("-version")
    for method in existing:
        if (
            method.formula == formula
            and method.inputs_structure == inputs
            and method.unit == unit
            and method.kebs_reference == METHOD_REFERENCE
        ):
            return method

    version = (existing.aggregate(value=Max("version"))["value"] or 0) + 1
    hash_payload = json.dumps(
        {
            "method": method_name,
            "reference": METHOD_REFERENCE,
            "formula": formula,
            "inputs": inputs,
            "unit": unit,
            "precision": 4,
            "rounding_mode": "HALF_UP",
            "version": version,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return Method.objects.using(database).create(
        method=method_name,
        version=version,
        is_active=True,
        kebs_reference=METHOD_REFERENCE,
        formula=formula,
        inputs_structure=inputs,
        unit=unit,
        rounding_precision=4,
        rounding_mode="HALF_UP",
        description=description,
        category="Aluminium sulphate standardization",
        tags=tags,
        formula_hash=hashlib.sha256(hash_payload.encode()).hexdigest(),
    )


def _new_specification(Specification, Remark, database, previous, method):
    previous.is_active = False
    previous.save(using=database, update_fields=["is_active"])
    current = Specification.objects.using(database).create(
        chemical_id=previous.chemical_id,
        treatment_plant_id=previous.treatment_plant_id,
        parameter_name=previous.parameter_name,
        unit=previous.unit,
        method_id=method.pk,
        min_limit=previous.min_limit,
        max_limit=previous.max_limit,
        is_required=previous.is_required,
        is_active=True,
        requires_instrument=previous.requires_instrument,
        version=previous.version + 1,
    )
    remarks = Remark.objects.using(database).filter(specification_id=previous.pk)
    Remark.objects.using(database).bulk_create(
        [
            Remark(specification_id=current.pk, on_pass=item.on_pass, on_fail=item.on_fail)
            for item in remarks
        ]
    )


def configure_alum_standardization(apps, schema_editor):
    database = schema_editor.connection.alias
    Chemical = apps.get_model("ca", "Chemical")
    Specification = apps.get_model("ca", "ChemicalSpecification")
    Remark = apps.get_model("ca", "ChemicalSpecificationRemark")
    Method = apps.get_model("analysis_methods", "ChemicalAnalysisMethod")

    alum_ids = Chemical.objects.using(database).filter(
        models.Q(code__iexact="ALUM") | models.Q(name__icontains="Aluminium Sulphate")
    ).values_list("pk", flat=True)

    for specification in Specification.objects.using(database).filter(
        chemical_id__in=alum_ids,
        is_active=True,
    ).select_related("method").iterator(chunk_size=500):
        name = specification.parameter_name.casefold()
        if "zinc" in name and "chloride" in name:
            inputs = [
                {
                    "name": field,
                    "label": field,
                    "unit": "mL",
                    "help_text": f"Record zinc chloride titre volume {number}.",
                    "min_value": 0,
                    "required": True,
                }
                for field, number in (("Vol1", 1), ("Vol2", 2), ("Vol3", 3))
            ]
            method = _method_profile(
                Method,
                database,
                title="Zinc Chloride Volume",
                formula="(Vol1 + Vol2 + Vol3) / 3",
                inputs=inputs,
                unit=specification.unit,
                description="Enter three zinc chloride titre volumes. The reported zinc chloride volume is their arithmetic mean.",
                tags=["aluminium_sulphate", "zinc_chloride", "standardization"],
            )
        elif "edta" in name and any(
            word in name
            for word in ("normality", "concentration", "standardization", "standardisation")
        ):
            inputs = [
                {"name": field, "label": label, "unit": "mL", "min_value": 0, "required": True}
                for field, label in (
                    ("Reading1", "1st EDTA reading"),
                    ("Reading2", "2nd EDTA reading"),
                    ("Reading3", "3rd EDTA reading"),
                )
            ]
            method = _method_profile(
                Method,
                database,
                title="EDTA Standardization",
                formula="((Reading1 + Reading2 + Reading3) / 3) / 100",
                inputs=inputs,
                unit=specification.unit,
                description="Enter the first, second, and third EDTA standardization readings. EDTA normality is the arithmetic mean divided by 100 and is recorded as the established concentration.",
                tags=["aluminium_sulphate", "edta", "standardization", "established_concentration"],
            )
        else:
            continue

        if specification.method_id == method.pk:
            continue
        _new_specification(Specification, Remark, database, specification, method)


def reverse_alum_standardization(apps, schema_editor):
    # Keep versioned specifications and formula methods intact when reversing.
    # They may already have been used to record laboratory results.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ca", "0018_update_alum_hydrometer_formula"),
        ("analysis_methods", "0003_chemical_method_rounding_mode"),
    ]

    operations = [
        migrations.RunPython(configure_alum_standardization, reverse_alum_standardization),
    ]
