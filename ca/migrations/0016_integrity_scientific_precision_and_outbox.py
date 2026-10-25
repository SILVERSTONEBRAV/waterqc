from collections import defaultdict
import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q
import django.db.models.deletion
import django.utils.timezone


def normalize_existing_data(apps, schema_editor):
    db = schema_editor.connection.alias
    Batch = apps.get_model("ca", "ChemicalBatch")
    Sequence = apps.get_model("ca", "ChemicalBatchSequence")
    Checklist = apps.get_model("ca", "ChecklistForWaterTreatmentChemicalAnalysis")
    Result = apps.get_model("ca", "BatchTestResult")
    Specification = apps.get_model("ca", "ChemicalSpecification")
    Movement = apps.get_model("ca", "ChemicalInventoryMovement")

    legacy_statuses = Result.objects.using(db).exclude(
        status__isnull=True
    ).values_list("status", flat=True).distinct()
    for status in list(legacy_statuses):
        normalized = str(status or "").strip().upper()
        normalized = {"NOT APPLICABLE": "NA", "N/A": "NA"}.get(normalized, normalized)
        if normalized not in {"PASS", "FAIL", "NA"}:
            normalized = None
        if normalized != status:
            Result.objects.using(db).filter(status=status).update(status=normalized)
    Checklist.objects.using(db).filter(completed=True, completed_at__isnull=True).update(
        completed_at=F("updated_at")
    )
    Checklist.objects.using(db).filter(completed=False).exclude(completed_at__isnull=True).update(
        completed_at=None, completed_by_id=None
    )
    Batch.objects.using(db).filter(package_count=0).update(package_count=None)

    grouped = defaultdict(list)
    for spec in Specification.objects.using(db).order_by(
        "chemical_id", "parameter_name", "treatment_plant_id", "version", "pk"
    ).iterator(chunk_size=1000):
        grouped[(spec.chemical_id, spec.parameter_name, spec.treatment_plant_id)].append(spec)
    for specifications in grouped.values():
        used_versions = set()
        next_version = max((spec.version for spec in specifications), default=0) + 1
        active_ids = []
        for spec in specifications:
            if spec.version in used_versions:
                while next_version in used_versions:
                    next_version += 1
                Specification.objects.using(db).filter(pk=spec.pk).update(version=next_version)
                used_versions.add(next_version)
                next_version += 1
            else:
                used_versions.add(spec.version)
            if spec.is_active:
                active_ids.append(spec.pk)
        for stale_id in active_ids[:-1]:
            Specification.objects.using(db).filter(pk=stale_id).update(is_active=False)

    counters = defaultdict(int)
    for sample_id in Batch.objects.using(db).exclude(sample_id="").values_list("sample_id", flat=True).iterator():
        prefix, separator, suffix = sample_id.rpartition("-")
        if separator and suffix.isdigit():
            counters[prefix] = max(counters[prefix], int(suffix))
    for prefix, last_value in counters.items():
        Sequence.objects.using(db).update_or_create(
            prefix=prefix,
            defaults={"last_value": last_value},
        )

    last_by_batch = {}
    movements = Movement.objects.using(db).order_by("batch_id", "created_at", "pk")
    movement_updates = []
    for movement in movements.iterator():
        last_by_batch[movement.batch_id] = last_by_batch.get(movement.batch_id, 0) + 1
        movement.sequence = last_by_batch[movement.batch_id]
        movement_updates.append(movement)
        if len(movement_updates) >= 1000:
            Movement.objects.using(db).bulk_update(movement_updates, ["sequence"], batch_size=1000)
            movement_updates.clear()
    if movement_updates:
        Movement.objects.using(db).bulk_update(movement_updates, ["sequence"], batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("ca", "0015_remove_chemicalanalystqualification"),
        ("analysis_methods", "0002_alter_chemicalanalysismethod_method"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="chemicalbatch",
            name="unique_sample_id",
        ),
        migrations.AlterUniqueTogether(
            name="chemicalspecification",
            unique_together=set(),
        ),
        migrations.CreateModel(
            name="ChemicalBatchSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("prefix", models.CharField(max_length=160, unique=True)),
                ("last_value", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [models.CheckConstraint(condition=Q(last_value__gte=0), name="ca_batch_sequence_nonnegative")],
            },
        ),
        migrations.AlterField(
            model_name="chemicalbatch",
            name="quantity_received",
            field=models.DecimalField(decimal_places=6, max_digits=18),
        ),
        migrations.AlterField(
            model_name="chemicalbatch",
            name="package_count",
            field=models.PositiveIntegerField(blank=True, help_text="Total number of discrete packages, bags, drums, containers, or other sampling units in the batch.", null=True),
        ),
        migrations.AlterField(
            model_name="chemicalspecification",
            name="min_limit",
            field=models.DecimalField(blank=True, decimal_places=10, max_digits=24, null=True),
        ),
        migrations.AlterField(
            model_name="chemicalspecification",
            name="max_limit",
            field=models.DecimalField(blank=True, decimal_places=10, max_digits=24, null=True),
        ),
        migrations.AlterField(
            model_name="batchtestresult",
            name="value",
            field=models.DecimalField(blank=True, decimal_places=12, max_digits=26, null=True),
        ),
        migrations.AlterField(
            model_name="batchtestresult",
            name="revision_number",
            field=models.PositiveIntegerField(default=1, editable=False),
        ),
        migrations.AlterField(
            model_name="chemicalanalysisinput",
            name="calculated_value",
            field=models.DecimalField(blank=True, decimal_places=12, max_digits=26, null=True),
        ),
        migrations.AlterField(
            model_name="chemicalcoa",
            name="quantity",
            field=models.DecimalField(blank=True, decimal_places=6, editable=False, max_digits=18, null=True),
        ),
        migrations.AlterField(
            model_name="chemicalcoa",
            name="hash_version",
            field=models.PositiveSmallIntegerField(default=5, editable=False),
        ),
        migrations.AddField(
            model_name="chemicalcoa",
            name="approved_payload",
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
        migrations.AddField(
            model_name="chemicalcoa",
            name="pdf_sha256",
            field=models.CharField(blank=True, editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name="chemicalworkflowalert",
            name="acknowledged_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="acknowledged_chemical_workflow_alerts", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="chemicalinventorymovement",
            name="sequence",
            field=models.PositiveBigIntegerField(default=1),
        ),
        migrations.RunPython(normalize_existing_data, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="chemicalinventorymovement",
            name="ca_stock_batch_time_idx",
        ),
        migrations.AddIndex(
            model_name="chemicalinventorymovement",
            index=models.Index(fields=["batch", "sequence"], name="ca_stock_batch_sequence_idx"),
        ),
        migrations.AddConstraint(
            model_name="chemicalinventorymovement",
            constraint=models.UniqueConstraint(fields=("batch", "sequence"), name="ca_stock_batch_sequence_unique"),
        ),
        migrations.AddConstraint(
            model_name="chemicalinventorymovement",
            constraint=models.CheckConstraint(condition=Q(quantity_after__gte=0), name="ca_stock_balance_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="chemicalinventorymovement",
            constraint=models.CheckConstraint(condition=~Q(quantity_delta=0), name="ca_stock_delta_nonzero"),
        ),
        migrations.AddConstraint(
            model_name="chemicalinventorymovement",
            constraint=models.CheckConstraint(
                condition=Q(movement_type="RECEIPT", quantity_delta__gt=0)
                | Q(movement_type__in=["UTILIZATION", "RETURN"], quantity_delta__lt=0)
                | Q(movement_type="ADJUSTMENT"),
                name="ca_stock_movement_direction_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="chemicalbatch",
            constraint=models.CheckConstraint(condition=Q(status__in=["RECEIVED", "ANALYSED", "APPROVED", "REJECTED", "UTILIZED", "RETURNED"]), name="ca_batch_status_valid"),
        ),
        migrations.AddConstraint(
            model_name="chemicalbatch",
            constraint=models.CheckConstraint(condition=Q(quantity_received__gt=0), name="ca_batch_quantity_positive"),
        ),
        migrations.AddConstraint(
            model_name="chemicalbatch",
            constraint=models.CheckConstraint(condition=Q(quantity_utilized__isnull=True) | Q(quantity_utilized__gte=0), name="ca_batch_utilized_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="chemicalbatch",
            constraint=models.CheckConstraint(condition=Q(quantity_returned__isnull=True) | Q(quantity_returned__gte=0), name="ca_batch_returned_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="chemicalbatch",
            constraint=models.CheckConstraint(condition=Q(package_count__isnull=True) | Q(package_count__gte=1), name="ca_batch_package_count_positive"),
        ),
        migrations.AddIndex(
            model_name="chemicalbatch",
            index=models.Index(fields=["treatment_plant", "status", "-received_date"], name="ca_batch_plant_status_date_idx"),
        ),
        migrations.AddIndex(
            model_name="chemicalbatch",
            index=models.Index(fields=["chemical", "-received_date"], name="ca_batch_chemical_date_idx"),
        ),
        migrations.AddConstraint(
            model_name="chemicalspecification",
            constraint=models.UniqueConstraint(fields=("chemical", "parameter_name", "version", "treatment_plant"), name="ca_spec_version_plant_unique", nulls_distinct=False),
        ),
        migrations.AddConstraint(
            model_name="chemicalspecification",
            constraint=models.UniqueConstraint(condition=Q(is_active=True), fields=("chemical", "parameter_name", "treatment_plant"), name="ca_one_active_spec_per_plant", nulls_distinct=False),
        ),
        migrations.AddConstraint(
            model_name="chemicalspecification",
            constraint=models.CheckConstraint(condition=Q(min_limit__isnull=True) | Q(max_limit__isnull=True) | Q(min_limit__lte=F("max_limit")), name="ca_spec_min_lte_max"),
        ),
        migrations.AddConstraint(
            model_name="chemicalspecification",
            constraint=models.CheckConstraint(condition=Q(version__gte=1), name="ca_spec_version_positive"),
        ),
        migrations.AddConstraint(
            model_name="batchtestresult",
            constraint=models.CheckConstraint(condition=Q(status__isnull=True) | Q(status__in=["PASS", "FAIL", "NA"]), name="ca_result_status_valid"),
        ),
        migrations.AddConstraint(
            model_name="batchtestresult",
            constraint=models.CheckConstraint(condition=Q(revision_number__gte=1), name="ca_result_revision_positive"),
        ),
        migrations.AddConstraint(
            model_name="checklistforwatertreatmentchemicalanalysis",
            constraint=models.CheckConstraint(condition=Q(completed=False, completed_at__isnull=True) | Q(completed=True, completed_at__isnull=False), name="ca_checklist_completion_timestamp_consistent"),
        ),
        migrations.AddConstraint(
            model_name="chemicalbatchhold",
            constraint=models.CheckConstraint(condition=Q(status__in=["OPEN", "RESOLVED", "REJECTED"]), name="ca_batch_hold_status_valid"),
        ),
        migrations.AddConstraint(
            model_name="chemicalcorrectiveaction",
            constraint=models.CheckConstraint(condition=Q(status__in=["OPEN", "VERIFIED", "REJECTED"]), name="ca_capa_status_valid"),
        ),
        migrations.AddConstraint(
            model_name="chemicalanalysisrequest",
            constraint=models.CheckConstraint(condition=Q(status__in=["PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED"]), name="ca_request_status_valid"),
        ),
        migrations.CreateModel(
            name="ChemicalCoAAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("APPROVED", "Approved"), ("REVOKED", "Approval revoked")], max_length=16)),
                ("content_hash", models.CharField(blank=True, max_length=64)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("coa", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audit_events", to="ca.chemicalcoa")),
            ],
            options={
                "ordering": ["-occurred_at", "-pk"],
                "indexes": [models.Index(fields=["coa", "occurred_at"], name="ca_coa_audit_time_idx")],
            },
        ),
        migrations.CreateModel(
            name="ChemicalOutboxEvent",
            fields=[
                ("event_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.CharField(max_length=180, unique=True)),
                ("event_type", models.CharField(db_index=True, max_length=80)),
                ("aggregate_type", models.CharField(max_length=80)),
                ("aggregate_id", models.CharField(max_length=80)),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("available_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
            ],
            options={
                "ordering": ["created_at", "event_id"],
                "indexes": [models.Index(fields=["delivered_at", "available_at"], name="ca_outbox_pending_idx")],
                "constraints": [models.CheckConstraint(condition=Q(attempt_count__gte=0), name="ca_outbox_attempts_nonnegative")],
            },
        ),
        migrations.CreateModel(
            name="ChemicalSuperuserPurgeAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("root_model", models.CharField(max_length=120)),
                ("root_ids", models.JSONField(default=list)),
                ("root_labels", models.JSONField(default=list)),
                ("deleted_counts", models.JSONField(default=dict)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-occurred_at", "-pk"]},
        ),
    ]
