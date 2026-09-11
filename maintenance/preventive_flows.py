# maintenance/preventive_flows.py

from django.conf import settings
from django.utils import timezone
from django.db import models, transaction
from django.views.generic import UpdateView

from viewflow.workflow import flow
from viewflow.workflow.models import Process

from .models import (
    MaintenanceSchedule,
    WorkOrder,
    WorkOrderApproval,
    MaintenanceChecklist,
    MaintenanceChecklistItem,
    WorkMaterialUsage,
    WorkOrderLabor,
    MaintenanceAssetHistory,
    MaintenanceAuditLog,
    MaintenanceKPI,
)


# =========================================================
# PROCESS MODEL
# =========================================================

class PreventiveMaintenanceProcess(Process):

    schedule = models.ForeignKey(
        "maintenance.MaintenanceSchedule",
        on_delete=models.CASCADE,
        related_name="processes"
    )

    work_order = models.OneToOneField(
        "maintenance.WorkOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preventive_process"
    )

    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    started_at = models.DateTimeField(
        auto_now_add=True
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Preventive Maintenance Process"
        verbose_name_plural = "Preventive Maintenance Processes"


# =========================================================
# FLOW
# =========================================================

class PreventiveMaintenanceFlow(flow.Flow):

    process_class = PreventiveMaintenanceProcess

    process_title = "Preventive Maintenance Workflow"

    process_description = (
        "Scheduled maintenance workflow for equipment and duty houses"
    )

    # =====================================================
    # START
    # =====================================================

    start = flow.StartFunction(
        func="_generate_work_order"
    )

    @staticmethod
    @transaction.atomic
    def _generate_work_order(activation):

        schedule = activation.process.schedule

        order = WorkOrder.objects.create(
            maintenance_type="preventive",
            priority=schedule.priority,
            target_type=schedule.target_type,
            duty_house=schedule.duty_house,
            equipment=schedule.equipment,
            scheduled_at=timezone.now(),
            estimated_cost=schedule.estimated_cost,
        )

        activation.process.work_order = order
        activation.process.started_by = activation.user

        activation.process.save(
            update_fields=[
                "work_order",
                "started_by",
            ]
        )

    # =====================================================
    # APPROVAL CHECK
    # =====================================================

    approval_required = flow.If(
        cond=lambda act:
        act.process.schedule.requires_approval
    )

    # =====================================================
    # APPROVAL
    # =====================================================

    approval = flow.View(
        UpdateView.as_view(
            model=WorkOrderApproval,
            fields=[
                "decision",
                "comments",
            ],
        )
    ).Permission(
        "maintenance.approve_workorder"
    )

    # =====================================================
    # ASSIGN TECHNICIAN
    # =====================================================

    assign = flow.View(
        UpdateView.as_view(
            model=WorkOrder,
            fields=[
                "assigned_to",
                "supervisor",
                "scheduled_at",
            ],
        )
    ).Permission(
        "maintenance.assign_workorder"
    )

    # =====================================================
    # START WORK
    # =====================================================

    start_work = flow.Function(
        func="_start_work"
    )

    @staticmethod
    def _start_work(activation):

        order = activation.process.work_order

        order.start()

    # =====================================================
    # CHECKLIST EXECUTION
    # =====================================================

    execute_checklist = flow.View(
        UpdateView.as_view(
            model=MaintenanceChecklist,
            fields=[]
        )
    ).Permission(
        "maintenance.execute_checklist"
    )

    # =====================================================
    # CHECKLIST VALIDATION
    # =====================================================

    validate_checklist = flow.Function(
        func="_validate_checklist"
    )

    @staticmethod
    def _validate_checklist(activation):

        order = activation.process.work_order

        incomplete_items = (
            MaintenanceChecklistItem.objects
            .filter(
                checklist__work_order=order,
                is_completed=False
            )
            .exists()
        )

        if incomplete_items:
            raise Exception(
                "Checklist contains incomplete items."
            )

    # =====================================================
    # RECORD MATERIALS
    # =====================================================

    materials = flow.View(
        UpdateView.as_view(
            model=WorkMaterialUsage,
            fields=[
                "inventory_item",
                "quantity_used",
                "unit_cost",
            ],
        )
    ).Permission(
        "maintenance.use_inventory"
    )

    # =====================================================
    # RECORD LABOR
    # =====================================================

    labor = flow.View(
        UpdateView.as_view(
            model=WorkOrderLabor,
            fields=[
                "employee",
                "hours_worked",
                "hourly_rate",
            ],
        )
    ).Permission(
        "maintenance.add_workorderlabor"
    )

    # =====================================================
    # VERIFICATION
    # =====================================================

    verification = flow.View(
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
    # UPDATE HISTORY
    # =====================================================

    update_history = flow.Function(
        func="_update_history"
    )

    @staticmethod
    def _update_history(activation):

        order = activation.process.work_order

        MaintenanceAssetHistory.objects.create(
            work_order=order,
            event_type="preventive_maintenance",
            title="Scheduled Preventive Maintenance",
            event_date=timezone.now(),
        )

    # =====================================================
    # KPI UPDATE
    # =====================================================

    update_kpi = flow.Function(
        func="_update_kpi"
    )

    @staticmethod
    def _update_kpi(activation):

        now = timezone.now()

        kpi, _ = MaintenanceKPI.objects.get_or_create(
            year=now.year,
            month=now.month
        )

        kpi.preventive_work_orders += 1

        kpi.save(
            update_fields=[
                "preventive_work_orders"
            ]
        )

    # =====================================================
    # RECALCULATE NEXT DUE DATE
    # =====================================================

    recalculate_schedule = flow.Function(
        func="_recalculate_schedule"
    )

    @staticmethod
    def _recalculate_schedule(activation):

        schedule = activation.process.schedule

        schedule.last_completed_at = timezone.now()

        schedule.calculate_next_due_date()

        schedule.save(
            update_fields=[
                "last_completed_at",
                "next_due_date",
            ]
        )

    # =====================================================
    # COMPLETE ORDER
    # =====================================================

    complete_order = flow.Function(
        func="_complete_order"
    )

    @staticmethod
    def _complete_order(activation):

        order = activation.process.work_order

        order.complete()

        MaintenanceAuditLog.objects.create(
            action="PREVENTIVE_MAINTENANCE_COMPLETED",
            work_order=order,
            performed_by=activation.user,
        )

        activation.process.completed_at = timezone.now()

        activation.process.save(
            update_fields=[
                "completed_at"
            ]
        )

    # =====================================================
    # END
    # =====================================================

    end = flow.End()

    # =====================================================
    # TRANSITIONS
    # =====================================================

    start.Next(approval_required)

    approval_required.Then(
        approval
    ).Else(
        assign
    )

    approval.Next(assign)

    assign.Next(start_work)

    start_work.Next(execute_checklist)

    execute_checklist.Next(validate_checklist)

    validate_checklist.Next(materials)

    materials.Next(labor)

    labor.Next(verification)

    verification.Next(update_history)

    update_history.Next(update_kpi)

    update_kpi.Next(recalculate_schedule)

    recalculate_schedule.Next(complete_order)

    complete_order.Next(end)