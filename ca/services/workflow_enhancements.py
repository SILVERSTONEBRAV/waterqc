"""Shared audit, custody, hold, and stock-ledger helpers for CA workflow actions."""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from ca.models import (
    ChemicalBatchHold,
    ChemicalCustodyEvent,
    ChemicalInventoryMovement,
    ChemicalWorkflowEvent,
    ChemicalWorkflowAlert,
    ChemicalAnalysisProcess,
)


import datetime
from decimal import Decimal
from uuid import UUID


def _json_safe(val):
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    if isinstance(val, UUID):
        return str(val)
    if isinstance(val, dict):
        return {k: _json_safe(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_json_safe(v) for v in val]
    return val


def record_workflow_event(
    process,
    *,
    event_type,
    action="",
    actor=None,
    from_status="",
    to_status="",
    details=None,
):
    if process is None or not process.batch_id:
        return None
    event = ChemicalWorkflowEvent.objects.create(
        process=process,
        batch=process.batch,
        analysis_request=process.analysis_request if process.analysis_request_id else None,
        event_type=str(event_type),
        action=str(action or ""),
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        from_status=str(from_status or ""),
        to_status=str(to_status or ""),
        details=_json_safe(details or {}),
    )
    try:
        from ca.signals import broadcast_dashboard_event

        transaction.on_commit(lambda: broadcast_dashboard_event(
            "chemical_workflow_event",
            {
                "event_id": event.pk,
                "batch_id": process.batch_id,
                "process_id": process.pk,
                "event_type": event.event_type,
                "status": event.to_status or process.status,
            },
        ))
    except Exception:
        # Audit data is already durable; live dashboard refresh is best-effort.
        pass
    return event


def record_custody_event(
    batch,
    *,
    event_type,
    actor=None,
    from_location="",
    to_location="",
    seal_number="",
    remarks="",
    evidence=None,
):
    if batch is None:
        return None
    event = ChemicalCustodyEvent(
        batch=batch,
        event_type=event_type,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        from_location=str(from_location or ""),
        to_location=str(to_location or ""),
        seal_number=str(seal_number or ""),
        remarks=str(remarks or ""),
        evidence=evidence,
    )
    event.save()
    return event


def record_intake_holds(batch, *, issues, details, actor):
    issues = list(dict.fromkeys(issues or []))
    if not issues:
        return []
    details = str(details or "").strip()
    if not details:
        raise ValidationError("Describe the intake discrepancy before placing the batch on hold.")
    holds = [
        ChemicalBatchHold.objects.create(
            batch=batch,
            issue=issue,
            details=details,
            opened_by=actor,
        )
        for issue in issues
    ]
    from ca.services.workflow_notifications import create_workflow_alert

    for hold in holds:
        create_workflow_alert(
            batch=batch,
            alert_type="ca_batch_hold",
            title="Chemical batch is on intake hold",
            message=f"{hold.get_issue_display()}: {hold.details}",
            url=f"/ca/batches/{batch.pk}/",
            severity="high",
            dedupe_key=f"intake-hold:{hold.pk}",
            permissions=("ca.resolve_chemical_batch_hold", "ca.view_chemicalanalysisprocess"),
        )
    return holds


@transaction.atomic
def resolve_batch_hold(hold, *, actor, resolution, reject=False):
    hold = ChemicalBatchHold.objects.select_for_update().select_related("batch").get(pk=hold.pk)
    if not actor or not actor.is_authenticated:
        raise PermissionDenied("Sign in to resolve a chemical batch hold.")
    if not actor.is_superuser:
        if not actor.has_perm("ca.resolve_chemical_batch_hold"):
            raise PermissionDenied("You do not have permission to resolve this hold.")
        plant_id = getattr(actor, "assigned_treatment_plant_id", None)
        if plant_id != hold.batch.treatment_plant_id:
            raise PermissionDenied("This batch is outside your treatment-plant scope.")
    result = hold.resolve(actor=actor, resolution=resolution, reject=reject)
    ChemicalWorkflowAlert.objects.filter(
        batch=hold.batch,
        alert_type="ca_batch_hold",
        dedupe_key=f"intake-hold:{hold.pk}",
        acknowledged_at__isnull=True,
    ).update(acknowledged_at=timezone.now(), acknowledged_by=actor)
    try:
        process = hold.batch.analysis_process
    except ChemicalAnalysisProcess.DoesNotExist:
        process = None
    if process:
        old_status = process.status
        if reject:
            process.mark_rejected(
                performed_by=actor,
                reason=resolution,
                permission="ca.resolve_chemical_batch_hold",
            )
            if process.analysis_request_id and process.analysis_request.status in {
                process.analysis_request.Status.PENDING,
                process.analysis_request.Status.IN_PROGRESS,
            }:
                process.analysis_request.transition_to(
                    process.analysis_request.Status.CANCELLED,
                    performed_by=actor,
                )
        record_workflow_event(
            process,
            event_type="batch_hold_closed",
            action=result.status,
            actor=actor,
            from_status=old_status,
            to_status=process.status if reject else "HOLD_RELEASED",
            details={"hold_id": result.pk, "issue": result.issue, "resolution": result.resolution},
        )
    return result


def record_inventory_movement(batch, *, movement_type, quantity, actor, idempotency_key, notes=""):
    return ChemicalInventoryMovement.record(
        batch=batch,
        movement_type=movement_type,
        quantity=quantity,
        actor=actor,
        idempotency_key=idempotency_key,
        notes=notes,
    )


def get_stage_duration_metrics(processes, *, now=None):
    """Summarize completed and current stage age from the workflow journal."""
    now = now or timezone.now()
    process_ids = [process.pk for process in processes if getattr(process, "pk", None)]
    if not process_ids:
        return {"stages": [], "active_processes": 0, "average_hours": 0}
    events = ChemicalWorkflowEvent.objects.filter(
        process_id__in=process_ids,
        event_type__in=("process_created", "process_status_changed"),
    ).values_list("process_id", "to_status", "occurred_at").order_by("process_id", "occurred_at", "pk")
    by_process = defaultdict(list)
    for process_id, status, occurred_at in events:
        if occurred_at:
            by_process[process_id].append((str(status or "").upper(), occurred_at))
    durations = defaultdict(list)
    active = 0
    for process in processes:
        history = by_process.get(process.pk, [])
        if not history:
            started = getattr(process, "created_at", None)
            if started:
                history = [(str(process.status or "").upper(), started)]
        for index, (status, entered_at) in enumerate(history):
            ended_at = history[index + 1][1] if index + 1 < len(history) else now
            seconds = max(0, (ended_at - entered_at).total_seconds())
            if status:
                durations[status].append(seconds)
        if str(getattr(process, "status", "")).upper() not in {
            ChemicalAnalysisProcess.WorkflowStatus.COMPLETED,
            ChemicalAnalysisProcess.WorkflowStatus.REJECTED,
            ChemicalAnalysisProcess.WorkflowStatus.UTILIZED,
            ChemicalAnalysisProcess.WorkflowStatus.RETURNED,
        }:
            active += 1
    stages = []
    for status, samples in sorted(durations.items()):
        stages.append({
            "status": status,
            "count": len(samples),
            "average_hours": round(sum(samples) / len(samples) / 3600, 2),
            "median_hours": round(median(samples) / 3600, 2),
            "oldest_hours": round(max(samples) / 3600, 2),
        })
    overall = [duration for samples in durations.values() for duration in samples]
    return {
        "stages": stages,
        "active_processes": active,
        "average_hours": round(sum(overall) / len(overall) / 3600, 2) if overall else 0,
    }
