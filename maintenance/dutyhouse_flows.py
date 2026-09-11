from django.conf import settings
from django.utils import timezone
from django.db import models, transaction
from django.views.generic import CreateView, UpdateView

from viewflow.workflow import flow
from viewflow.workflow.models import Process

from django.contrib.auth import get_user_model

from maintenance.models import WorkRequest, WorkOrder, WorkTask

User = get_user_model()


# =========================================================
# PROCESS MODEL (ENHANCED META-DRIVEN ENGINE)
# =========================================================

class DutyHouseMaintenanceProcess(Process):
    request = models.OneToOneField(
        WorkRequest,
        on_delete=models.CASCADE,
        related_name="vf_process",
    )

    order = models.OneToOneField(
        WorkOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vf_process",
    )

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duty_house_flow_reports",
    )

    housing_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duty_house_flow_approvals",
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duty_house_flow_assignments",
    )

    current_stage = models.CharField(max_length=50, default="start")

    sla_status = models.CharField(max_length=20, default="active")

    completed_at = models.DateTimeField(null=True, blank=True)

    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Duty House Maintenance Process"


# =========================================================
# VIEWS (STRICT INPUT CONTROL + SAFE BINDING)
# =========================================================

class WorkRequestCreateView(CreateView):
    model = WorkRequest
    fields = [
        "title",
        "description",
        "priority",
        "target_type",
        "duty_house_number",
        "is_emergency",
    ]

    def form_valid(self, form):
        activation = getattr(self.request, "activation", None)

        if activation:
            form.instance.reported_by = activation.user
            form.instance.status = "pending"

        return super().form_valid(form)


class WorkOrderUpdateView(UpdateView):
    model = WorkOrder
    fields = ["assigned_to", "supervisor", "scheduled_at", "metadata"]


# =========================================================
# FLOW ENGINE
# =========================================================

class DutyHouseMaintenanceFlow(flow.Flow):

    process_class = DutyHouseMaintenanceProcess

    process_title = "Duty House Maintenance Workflow"

    process_description = "Fully automated duty house maintenance lifecycle with SLA + escalation engine"

    # -----------------------------------------------------
    # START
    # -----------------------------------------------------
    start = flow.Start(
        WorkRequestCreateView.as_view()
    ).Permission("maintenance.add_workrequest")

    # -----------------------------------------------------
    # ENRICH REQUEST (INTELLIGENCE LAYER)
    # -----------------------------------------------------
    enrich_request = flow.Function(func="_enrich_request")

    @staticmethod
    @transaction.atomic
    def _enrich_request(activation):
        req = activation.process.request

        activation.process.meta.update({
            "source": "duty_house_portal",
            "priority_snapshot": req.priority,
            "emergency_flag": req.is_emergency,
            "ingested_at": timezone.now().isoformat(),
        })

        activation.process.reported_by = activation.user
        activation.process.current_stage = "enriched"

        activation.process.save(update_fields=["meta", "reported_by", "current_stage"])

    # -----------------------------------------------------
    # REVIEW STAGE
    # -----------------------------------------------------
    housing_officer_review = flow.View(
        UpdateView.as_view(
            model=WorkRequest,
            fields=["status", "metadata"],
        )
    ).Permission("maintenance.change_workrequest")

    # -----------------------------------------------------
    # DECISION ENGINE (RULE-BASED ROUTING)
    # -----------------------------------------------------
    decide = flow.Function(func="_decide")

    @staticmethod
    def _decide(activation):
        req = activation.process.request

        # emergency bypass path
        if req.is_emergency:
            return activation.flow.auto_approve

        # SLA-aware routing hook
        if req.priority == "critical":
            return activation.flow.fast_track

        return activation.flow.approve_route

    # -----------------------------------------------------
    # FAST TRACK (HIGH PRIORITY AUTO ESCALATION PATH)
    # -----------------------------------------------------
    fast_track = flow.Function(func="_fast_track")

    @staticmethod
    @transaction.atomic
    def _fast_track(activation):
        req = activation.process.request

        req.status = "approved"
        req.approved_by = activation.user
        req.approved_at = timezone.now()
        req.save(update_fields=["status", "approved_by", "approved_at"])

        activation.process.meta["fast_track"] = True
        activation.process.housing_officer = activation.user

        activation.process.save(update_fields=["meta", "housing_officer"])

    # -----------------------------------------------------
    # AUTO APPROVE
    # -----------------------------------------------------
    auto_approve = flow.Function(func="_auto_approve")

    @staticmethod
    @transaction.atomic
    def _auto_approve(activation):
        req = activation.process.request

        req.status = "approved"
        req.approved_by = activation.user
        req.approved_at = timezone.now()
        req.save(update_fields=["status", "approved_by", "approved_at"])

        activation.process.meta["auto_approved"] = True
        activation.process.housing_officer = activation.user

        activation.process.save(update_fields=["meta", "housing_officer"])

    # -----------------------------------------------------
    # MANUAL APPROVAL
    # -----------------------------------------------------
    approve_route = flow.Function(func="_approve")

    @staticmethod
    @transaction.atomic
    def _approve(activation):
        req = activation.process.request

        req.status = "approved"
        req.approved_by = activation.user
        req.approved_at = timezone.now()
        req.save(update_fields=["status", "approved_by", "approved_at"])

        activation.process.housing_officer = activation.user
        activation.process.save(update_fields=["housing_officer"])

    # -----------------------------------------------------
    # REJECT
    # -----------------------------------------------------
    reject = flow.Function(func="_reject")

    @staticmethod
    @transaction.atomic
    def _reject(activation):
        req = activation.process.request

        req.status = "rejected"
        req.metadata["rejection"] = {
            "by": str(activation.user),
            "time": timezone.now().isoformat(),
        }

        req.save(update_fields=["status", "metadata"])

        activation.process.current_stage = "rejected"
        activation.process.save(update_fields=["current_stage"])

    # -----------------------------------------------------
    # ORDER CREATION (CORE TRANSITION)
    # -----------------------------------------------------
    create_order = flow.Function(func="_create_order")

    @staticmethod
    @transaction.atomic
    def _create_order(activation):
        req = activation.process.request

        order = WorkOrder.objects.create(
            request=req,
            priority=req.priority,
            metadata={
                "origin": "duty_house_flow",
                "duty_house_number": req.duty_house_number,
                "sla_hint": req.priority,
            },
        )

        activation.process.order = order
        activation.process.current_stage = "order_created"

        activation.process.save(update_fields=["order", "current_stage"])

    # -----------------------------------------------------
    # ASSIGN TEAM
    # -----------------------------------------------------
    assign_team = flow.View(
        WorkOrderUpdateView.as_view()
    ).Permission("maintenance.change_workorder")

    assign_finalize = flow.Function(func="_assign_finalize")

    @staticmethod
    @transaction.atomic
    def _assign_finalize(activation):
        order = activation.process.order

        order.status = "assigned"
        order.metadata = order.metadata or {}
        order.metadata["assignment"] = {
            "by": str(activation.user),
            "time": timezone.now().isoformat(),
        }

        order.save(update_fields=["status", "metadata"])

        activation.process.assigned_by = activation.user
        activation.process.current_stage = "assigned"

        activation.process.save(update_fields=["assigned_by", "current_stage"])

    # -----------------------------------------------------
    # EXECUTION START
    # -----------------------------------------------------
    start_execution = flow.Function(func="_start_execution")

    @staticmethod
    @transaction.atomic
    def _start_execution(activation):
        order = activation.process.order

        order.status = "in_progress"
        order.started_at = timezone.now()

        order.save(update_fields=["status", "started_at"])

        activation.process.current_stage = "execution"
        activation.process.save(update_fields=["current_stage"])

    # -----------------------------------------------------
    # SLA + MONITORING HOOK (EXTENSION POINT)
    # -----------------------------------------------------
    monitor = flow.Function(func="_monitor")

    @staticmethod
    def _monitor(activation):
        # This is intentionally a hook:
        # connect SLA engine, incident escalation, or KPI tracking here
        activation.process.meta["monitor_tick"] = timezone.now().isoformat()
        activation.process.save(update_fields=["meta"])

    # -----------------------------------------------------
    # CLOSE WORK
    # -----------------------------------------------------
    close_work = flow.Function(func="_close")

    @staticmethod
    @transaction.atomic
    def _close(activation):
        req = activation.process.request
        order = activation.process.order

        order.status = "completed"
        order.completed_at = timezone.now()
        order.save(update_fields=["status", "completed_at"])

        req.status = "closed"
        req.save(update_fields=["status"])

        activation.process.completed_at = timezone.now()
        activation.process.current_stage = "completed"

        activation.process.save(update_fields=["completed_at", "current_stage"])

    # -----------------------------------------------------
    # END
    # -----------------------------------------------------
    end = flow.End()


# =========================================================
# FLOW CONNECTIVITY
# =========================================================

start.Next(enrich_request)
enrich_request.Next(housing_officer_review)

housing_officer_review.Next(decide)

decide.Next(auto_approve)
decide.Next(approve_route)
decide.Next(fast_track)

auto_approve.Next(create_order)
approve_route.Next(create_order)
fast_track.Next(create_order)

create_order.Next(assign_team)
assign_team.Next(assign_finalize)

assign_finalize.Next(start_execution)

start_execution.Next(monitor)

monitor.Then(start_execution).Else(close_work)

close_work.Next(end)