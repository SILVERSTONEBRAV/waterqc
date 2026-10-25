"""Permission-aware, plant-scoped CA reminders and SLA escalation."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ca.models import (
    ChemicalAnalysisProcess,
    ChemicalAnalysisRequest,
    ChemicalBatch,
    ChemicalBatchHold,
    ChemicalWorkflowAlert,
)

logger = logging.getLogger(__name__)


def _eligible_users(batch, permissions):
    User = get_user_model()
    users = User.objects.filter(is_active=True)
    if batch.treatment_plant_id:
        users = users.filter(
            Q(assigned_treatment_plant_id=batch.treatment_plant_id) | Q(is_superuser=True)
        )
    recipients = []
    for user in users.iterator(chunk_size=200):
        if user.is_superuser or any(user.has_perm(permission) for permission in permissions):
            recipients.append(user)
    return recipients


@transaction.atomic
def create_workflow_alert(
    *, batch, alert_type, title, message, url, severity="medium", dedupe_key,
    permissions, request=None, exclude_user_ids=(),
):
    created = []
    excluded_ids = {int(value) for value in (exclude_user_ids or ()) if value is not None}
    for recipient in _eligible_users(batch, permissions):
        if recipient.pk in excluded_ids:
            continue
        alert, was_created = ChemicalWorkflowAlert.objects.get_or_create(
            recipient=recipient,
            dedupe_key=str(dedupe_key),
            defaults={
                "batch": batch,
                "analysis_request": request,
                "alert_type": str(alert_type),
                "title": str(title)[:180],
                "message": str(message),
                "url": str(url),
                "severity": str(severity).lower(),
            },
        )
        if was_created:
            created.append(alert)
    if created:
        try:
            # Generate persistent voice alert for the workflow notification
            from alerts.models import VoiceAlert
            sample_item = created[0]
            voice_msg = f"{sample_item.title}. {sample_item.message}"
            transaction.on_commit(lambda: VoiceAlert.generate_persistent_voice_alert(
                message=voice_msg,
                title=sample_item.title,
            ))
        except Exception as v_err:
            logger.warning(f"Could not generate voice alert for CA workflow notification: {v_err}")

        try:
            from ca.signals import broadcast_dashboard_event

            transaction.on_commit(lambda: broadcast_dashboard_event(
                "chemical_workflow_alert",
                {
                    "alert_ids": [item.pk for item in created],
                    "batch_id": batch.pk,
                    "alert_type": alert_type,
                    "plant_id": batch.treatment_plant_id,
                },
            ))
        except Exception:
            logger.exception("Could not broadcast a CA workflow notification")
    return created


def notify_analysis_assignment(analysis_request):
    """Notify the plant's analyst pool when a request gets assigned.

    Each analyst has a personal inbox row so plant scoping stays intact. The
    acknowledgement endpoint decides whether that analyst is one of the
    request's assignees; the batch list is the common landing page.
    """
    batch = getattr(analysis_request, "batch", None)
    if batch is None or not batch.pk:
        return []

    assigned = list(analysis_request.assigned_analysts.all())
    if not assigned:
        return []

    stamp = timezone.now()
    assignment_key = stamp.strftime("%Y%m%d%H%M%S%f")
    assigned_names = ", ".join(
        analyst.get_full_name() or analyst.get_username()
        for analyst in assigned
    )
    return create_workflow_alert(
        batch=batch,
        request=analysis_request,
        alert_type="ca_analysis_assignment",
        title="Chemical analysis request assigned",
        message=(
            f"Batch {batch.batch_number} is ready for its receiving checklist. "
            f"Assigned analyst(s): {assigned_names}."
        ),
        url=f"/ca/batches/?highlight={batch.pk}#batch-row-{batch.pk}",
        severity="medium",
        dedupe_key=f"analysis-assigned:{analysis_request.pk}:{assignment_key}",
        permissions=("ca.start_chemical_analysis",),
    )


def escalate_due_chemical_workflows(*, now=None):
    now = now or timezone.now()
    counts = {"assignment": 0, "analysis": 0, "holds": 0, "stalled": 0}

    due_assignments = (
        ChemicalAnalysisRequest.objects.filter(
            status=ChemicalAnalysisRequest.Status.PENDING,
            assigned_analysts__isnull=True,
        )
        .filter(
            Q(assignment_due_at__lte=now)
            | Q(assignment_due_at__isnull=True, created_at__lte=now - timedelta(minutes=30))
        )
        .select_related("batch", "batch__chemical")
        .distinct()
    )
    for request in due_assignments.iterator(chunk_size=100):
        batch = request.batch
        if not batch:
            continue
        try:
            assigned = request.auto_assign_analysts_if_due(now=now)
            if assigned.exists():
                try:
                    process = request.analysis_process
                except ChemicalAnalysisProcess.DoesNotExist:
                    process = None
                if process is not None:
                    from ca.chemical_flow import advance_analyst_assignment_workflow

                    advance_analyst_assignment_workflow(
                        process,
                        automatic=True,
                    )
                continue
            key_day = now.date().isoformat()
            created = create_workflow_alert(
                batch=batch,
                alert_type="ca_assignment_escalation",
                title="Chemical analysis has no assigned analyst",
                message=(
                    f"No scheduled analyst was available for {batch.chemical.name} "
                    f"batch {batch.batch_number}. Assign an eligible analyst or update the duty roster."
                ),
                url=f"/ca/requests/{request.pk}/assign-analyst/",
                severity="high",
                dedupe_key=f"assignment-overdue:{request.pk}:{key_day}",
                permissions=("ca.create_analysis_request",),
                request=request,
            )
            counts["assignment"] += len(created)
        except Exception:
            logger.exception("CA assignment escalation failed for request %s", request.pk)

    overdue = (
        ChemicalAnalysisRequest.objects.filter(
            status=ChemicalAnalysisRequest.Status.IN_PROGRESS,
            analysis_deadline__lt=now,
        )
        .select_related("batch", "batch__chemical")
        .distinct()
    )
    for request in overdue.iterator(chunk_size=100):
        batch = request.batch
        if not batch:
            continue
        try:
            created = create_workflow_alert(
                batch=batch,
                alert_type="ca_analysis_sla_escalation",
                title="Chemical analysis deadline missed",
                message=f"Analysis request {request.request_id} for batch {batch.batch_number} is overdue.",
                url=f"/ca/requests/{request.pk}/",
                severity="critical",
                dedupe_key=f"analysis-overdue:{request.pk}:{now.date().isoformat()}",
                permissions=("ca.start_chemical_analysis", "ca.complete_chemical_analysis", "ca.review_chemical_analysis"),
                request=request,
            )
            counts["analysis"] += len(created)
        except Exception:
            logger.exception("CA analysis SLA escalation failed for request %s", request.pk)

    open_holds = ChemicalBatchHold.objects.filter(
        status=ChemicalBatchHold.Status.OPEN,
    ).select_related("batch", "batch__chemical", "batch__analysis_process")
    for hold in open_holds.iterator(chunk_size=100):
        batch = hold.batch
        try:
            created = create_workflow_alert(
                batch=batch,
                alert_type="ca_batch_hold",
                title="Chemical batch is on intake hold",
                message=f"{hold.get_issue_display()}: {hold.details}",
                url=f"/ca/batches/{batch.pk}/",
                severity="high",
                dedupe_key=f"intake-hold:{hold.pk}",
                permissions=("ca.resolve_chemical_batch_hold", "ca.view_chemicalanalysisprocess"),
            )
            counts["holds"] += len(created)
        except Exception:
            logger.exception("CA hold reminder failed for hold %s", hold.pk)

    stalled_before = now - timedelta(hours=24)
    stalled = ChemicalAnalysisProcess.objects.filter(
        updated_at__lt=stalled_before,
        status__in=(
            ChemicalAnalysisProcess.WorkflowStatus.RECEIVED,
            ChemicalAnalysisProcess.WorkflowStatus.REQUESTED,
            ChemicalAnalysisProcess.WorkflowStatus.ASSIGNED,
            ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST,
            ChemicalAnalysisProcess.WorkflowStatus.ANALYSIS,
            ChemicalAnalysisProcess.WorkflowStatus.RETEST,
            ChemicalAnalysisProcess.WorkflowStatus.QA,
            ChemicalAnalysisProcess.WorkflowStatus.APPROVED,
        ),
    ).select_related("batch", "batch__chemical")
    for process in stalled.iterator(chunk_size=100):
        batch = process.batch
        if not batch or batch.has_active_holds:
            continue
        permission_by_status = {
            "RECEIVED": ("ca.receive_chemical_batch",),
            "REQUESTED": ("ca.create_analysis_request",),
            "ASSIGNED": ("ca.start_chemical_analysis",),
            "CHECKLIST": ("ca.complete_receiving_checklist",),
            "ANALYSIS": ("ca.record_chemical_result", "ca.complete_chemical_analysis"),
            "RETEST": ("ca.perform_chemical_retest", "ca.record_chemical_result"),
            "QA": ("ca.review_chemical_analysis", "ca.approve_chemical_batch"),
            "APPROVED": ("ca.approve_chemical_coa", "ca.utilize_chemical_batch", "ca.return_chemical_batch"),
        }
        try:
            created = create_workflow_alert(
                batch=batch,
                request=process.analysis_request if process.analysis_request_id else None,
                alert_type="ca_workflow_stalled",
                title="Chemical workflow needs attention",
                message=f"Batch {batch.batch_number} has remained in {dict(process.WorkflowStatus.choices).get(process.status, process.status)} for over 24 hours.",
                url=f"/ca/processes/{process.pk}/",
                severity="medium",
                dedupe_key=f"stalled:{process.pk}:{now.date().isoformat()}",
                permissions=permission_by_status.get(process.status, ("ca.view_chemicalanalysisprocess",)),
            )
            counts["stalled"] += len(created)
        except Exception:
            logger.exception("CA stalled-workflow alert failed for process %s", process.pk)

    return counts
