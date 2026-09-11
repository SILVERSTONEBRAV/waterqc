# inventory/tasks.py
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from decimal import Decimal

from .models import (
    InventoryItem,
    LaboratoryReagent,
    Equipment,
    AlertConfig,
    AuditLog,
)


# ---------------------------------------------------------------------
# AUDIT + ALERT UTILITIES
# ---------------------------------------------------------------------

def log_audit(instance, action: str, *, user=None, notes=None, section=None):
    """
    Generic audit logger (section-aware).
    """
    AuditLog.objects.create(
        content_type=ContentType.objects.get_for_model(instance.__class__),
        object_id=instance.pk,
        content_object=instance,
        action=action,
        user=user,
        section=section or getattr(instance, "section", None),
        notes=notes,
    )


def trigger_alert(alert: AlertConfig, item, message: str):
    """
    Fire an alert, send notifications, and persist audit trail.
    Prevents duplicate spamming via alert cooldown logic.
    """

    # Safety: section isolation
    if alert.section_id and getattr(item, "section_id", None) != alert.section_id:
        return

    # Prevent repeated alerts within cooldown window
    if not alert.should_fire_for(item):
        return

    try:
        alert.send_alert(item, message)
        notes = message
    except Exception as exc:
        notes = f"{message} | Notification failed: {exc}"

    log_audit(
        item,
        action="alert_triggered",
        section=item.section,
        notes=f"[{alert.name}] {notes}",
    )

    # Persist last-fired metadata (VERY important at scale)
    alert.mark_fired(item)


# ---------------------------------------------------------------------
# INVENTORY CHECKS
# ---------------------------------------------------------------------

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=60, retry_kwargs={"max_retries": 5})
def check_inventory_alerts(self):
    """
    Restock monitoring for InventoryItem.
    """
    alerts = AlertConfig.objects.filter(
        active=True,
        alert_type="restock",
    )

    for alert in alerts:
        items = InventoryItem.objects.filter(
            section=alert.section
        ).select_for_update()

        for item in items:
            with transaction.atomic():
                if alert.is_triggered_for(item):
                    message = (
                        f"Inventory '{item.name}' low: "
                        f"{item.quantity} < {alert.min_quantity or Decimal('1')}"
                    )
                    trigger_alert(alert, item, message)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=60, retry_kwargs={"max_retries": 5})
def check_reagent_alerts(self):
    """
    Expiry and restock alerts for LaboratoryReagent.
    """
    today = timezone.now().date()

    alerts = AlertConfig.objects.filter(
        active=True,
        alert_type__in=["restock", "expiry"],
    )

    for alert in alerts:
        reagents = LaboratoryReagent.objects.filter(
            section=alert.section
        ).select_for_update()

        for reagent in reagents:
            with transaction.atomic():
                if not alert.is_triggered_for(reagent):
                    continue

                if alert.alert_type == "expiry" and reagent.expiry_date:
                    days_left = (reagent.expiry_date - today).days
                    message = f"Reagent '{reagent.name}' expires in {days_left} day(s)"
                else:
                    message = (
                        f"Reagent '{reagent.name}' low: "
                        f"{reagent.quantity} < {alert.min_quantity or Decimal('1')}"
                    )

                trigger_alert(alert, reagent, message)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=60, retry_kwargs={"max_retries": 5})
def check_equipment_alerts(self):
    """
    Maintenance & calibration monitoring.
    """
    today = timezone.now().date()

    alerts = AlertConfig.objects.filter(
        active=True,
        alert_type__in=["maintenance_due", "calibration_due"],
    )

    for alert in alerts:
        equipments = Equipment.objects.filter(
            section=alert.section
        ).select_for_update()

        for eq in equipments:
            with transaction.atomic():
                if not alert.is_triggered_for(eq):
                    continue

                if alert.alert_type == "maintenance_due" and eq.next_maintenance_date:
                    days_left = (eq.next_maintenance_date - today).days
                    message = f"Equipment '{eq.name}' maintenance due in {days_left} day(s)"

                elif alert.alert_type == "calibration_due" and eq.calibration_due_date:
                    days_left = (eq.calibration_due_date - today).days
                    message = f"Equipment '{eq.name}' calibration due in {days_left} day(s)"

                else:
                    message = f"{alert.alert_type} triggered for '{eq.name}'"

                trigger_alert(alert, eq, message)


# ---------------------------------------------------------------------
# ORCHESTRATION TASKS
# ---------------------------------------------------------------------

@shared_task
def run_all_inventory_checks():
    """
    Single entry-point for Celery Beat.
    """
    check_inventory_alerts.delay()
    check_reagent_alerts.delay()
    check_equipment_alerts.delay()


@shared_task(bind=True)
def dynamic_alert_check(self, alert_id: int):
    """
    Run a single alert config immediately (testing or admin-triggered).
    """
    try:
        alert = AlertConfig.objects.get(pk=alert_id, active=True)
    except AlertConfig.DoesNotExist:
        raise ValueError(f"AlertConfig {alert_id} not found")

    model_map = {
        "restock": InventoryItem,
        "expiry": LaboratoryReagent,
        "maintenance_due": Equipment,
        "calibration_due": Equipment,
    }

    model = model_map.get(alert.alert_type)
    if not model:
        return

    items = model.objects.filter(section=alert.section)

    for item in items:
        with transaction.atomic():
            if alert.is_triggered_for(item):
                trigger_alert(alert, item, f"Manual alert check triggered")
