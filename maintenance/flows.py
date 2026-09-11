# maintenance/flows.py

from django.conf import settings
from django.utils import timezone
from django.db import models, transaction
from django.views.generic import CreateView, UpdateView
from viewflow.workflow import flow
from viewflow.workflow.models import Process

from .models import (
    WorkRequest,
    WorkOrder,
    MaintenanceIncident,
    WorkOrderApproval,
    WorkOrderEscalation,
    WorkOrderLabor,
    WorkMaterialUsage,
    MaintenanceAuditLog,
)

# =========================================================
# PROCESS MODEL
# =========================================================

class CorrectiveMaintenanceProcess(Process):

    request = models.OneToOneField(
        "maintenance.WorkRequest",
        on_delete=models.CASCADE,
        related_name="corrective_process"
    )

    work_order = models.OneToOneField(
        "maintenance.WorkOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="process"
    )

    incident = models.OneToOneField(
        "maintenance.MaintenanceIncident",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="process"
    )

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    started_at = models.DateTimeField(auto_now_add=True)

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )


# =========================================================
# VIEWS
# =========================================================

class IncidentCreateView(CreateView):
    model = MaintenanceIncident
    fields = [
        "title",
        "description",
        "severity",
        "incident_type",
        "root_cause",
    ]


class LaborCreateView(CreateView):
    model = WorkOrderLabor
    fields = [
        "employee",
        "hours_worked",
        "hourly_rate",
        "remarks",
    ]


class MaterialUsageCreateView(CreateView):
    model = WorkMaterialUsage
    fields = [
        "inventory_item",
        "quantity_used",
        "unit_cost",
    ]


# =========================================================
# FLOW
# =========================================================

class CorrectiveMaintenanceFlow(flow.Flow):

    process_class = CorrectiveMaintenanceProcess

    process_title = "Corrective Maintenance"

    # =====================================================
    # START REQUEST
    # =====================================================

    start = flow.Start(
        CreateView.as_view(
            model=WorkRequest,
            fields=[
                "title",
                "description",
                "priority",
                "target_type",
                "duty_house",
                "equipment",
                "is_emergency",
            ],
        )
    ).Permission(
        "maintenance.add_workrequest"
    )

    # =====================================================
    # INCIDENT REGISTRATION
    # =====================================================

    create_incident = flow.View(
        IncidentCreateView.as_view()
    ).Permission(
        "maintenance.add_maintenanceincident"
    )

    # =====================================================
    # RISK CLASSIFICATION
    # =====================================================

    classify_risk = flow.Function(
        func="_classify_risk"
    )

    @staticmethod
    def _classify_risk(activation):

        incident = activation.process.incident

        if incident.severity == "critical":
            activation.process.request.priority = "critical"

        elif incident.severity == "high":
            activation.process.request.priority = "high"

        activation.process.request.save(
            update_fields=["priority"]
        )

    # =====================================================
    # APPROVAL GATE
    # =====================================================

    approval_required = flow.If(
        cond=lambda act:
        act.process.request.priority in [
            "high",
            "critical"
        ]
    )

    approval = flow.View(
        UpdateView.as_view(
            model=WorkOrderApproval,
            fields=[
                "decision",
                "comments",
            ]
        )
    ).Permission(
        "maintenance.approve_workorder"
    )

    # =====================================================
    # CREATE WORK ORDER
    # =====================================================

    create_order = flow.Function(
        func="_create_order"
    )

    @staticmethod
    @transaction.atomic
    def _create_order(activation):

        request = activation.process.request

        order = WorkOrder.objects.create(
            request=request,
            priority=request.priority
        )

        activation.process.work_order = order

        activation.process.save(
            update_fields=["work_order"]
        )

    # =====================================================
    # ASSIGN TECHNICIAN
    # =====================================================

    assign_technician = flow.View(
        UpdateView.as_view(
            model=WorkOrder,
            fields=[
                "assigned_to",
                "supervisor",
                "scheduled_at",
            ]
        )
    ).Permission(
        "maintenance.assign_workorder"
    )

    # =====================================================
    # START REPAIR
    # =====================================================

    start_repair = flow.Function(
        func="_start_repair"
    )

    @staticmethod
    def _start_repair(activation):

        order = activation.process.work_order

        order.start()

    # =====================================================
    # LABOR CAPTURE
    # =====================================================

    labor_entry = flow.View(
        LaborCreateView.as_view()
    ).Permission(
        "maintenance.add_workorderlabor"
    )

    # =====================================================
    # MATERIALS CAPTURE
    # =====================================================

    material_entry = flow.View(
        MaterialUsageCreateView.as_view()
    ).Permission(
        "maintenance.add_workmaterialusage"
    )

    # =====================================================
    # SLA CHECK
    # =====================================================

    sla_monitor = flow.Function(
        func="_sla_monitor"
    )

    @staticmethod
    def _sla_monitor(activation):

        request = activation.process.request

        if hasattr(request, "sla"):
            request.sla.evaluate()

            if request.sla.status == "breached":

                WorkOrderEscalation.objects.create(
                    work_order=activation.process.work_order,
                    reason="SLA Breach"
                )

    # =====================================================
    # ROOT CAUSE ANALYSIS
    # =====================================================

    rca = flow.View(
        UpdateView.as_view(
            model=MaintenanceIncident,
            fields=[
                "root_cause",
                "corrective_action",
                "preventive_action",
            ]
        )
    ).Permission(
        "maintenance.perform_rca"
    )

    # =====================================================
    # VERIFY REPAIR
    # =====================================================

    verify = flow.View(
        UpdateView.as_view(
            model=WorkOrder,
            fields=[
                "verification_notes",
            ]
        )
    ).Permission(
        "maintenance.verify_workorder"
    )

    # =====================================================
    # COMPLETE
    # =====================================================

    complete = flow.Function(
        func="_complete"
    )

    @staticmethod
    def _complete(activation):

        order = activation.process.work_order

        order.complete()

        MaintenanceAuditLog.objects.create(
            action="WORK_ORDER_COMPLETED",
            work_order=order,
            performed_by=activation.user,
        )

        activation.process.completed_at = timezone.now()

        activation.process.save(
            update_fields=["completed_at"]
        )

    # =====================================================
    # END
    # =====================================================

    end = flow.End()

    # =====================================================
    # FLOW MAP
    # =====================================================

    start.Next(create_incident)

    create_incident.Next(classify_risk)

    classify_risk.Next(approval_required)

    approval_required.Then(approval).Else(create_order)

    approval.Next(create_order)

    create_order.Next(assign_technician)

    assign_technician.Next(start_repair)

    start_repair.Next(labor_entry)

    labor_entry.Next(material_entry)

    material_entry.Next(sla_monitor)

    sla_monitor.Next(rca)

    rca.Next(verify)

    verify.Next(complete)

    complete.Next(end)