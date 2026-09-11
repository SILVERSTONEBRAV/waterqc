# inventory/signals.py

from decimal import Decimal
from django.db import transaction
from django.db.models import F
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from alerts.engine import AlertEngine

from .models import (
    AuditLog,

    InventoryItem,
    InventoryTransaction,
    InventoryLog,

    LaboratoryReagent,
    LaboratoryReagentLog,

    Equipment,
    MaintenanceRecord,
    CalibrationRecord,
)

# =====================================================
# 🕵️ AUDIT LOGGING (CENTRALIZED & SAFE)
# =====================================================

AUDIT_MODELS = (
    InventoryItem, InventoryTransaction, InventoryLog,
    LaboratoryReagent, LaboratoryReagentLog,
    Equipment, MaintenanceRecord, CalibrationRecord,
)


def create_audit(instance, action: str, user=None, notes=None):
    """
    Central audit logger (safe against recursion).
    """
    if isinstance(instance, AuditLog):
        return

    if not isinstance(instance, AUDIT_MODELS):
        return

    AuditLog.objects.create(
        content_type=ContentType.objects.get_for_model(instance.__class__),
        object_id=instance.pk,
        action=action,
        user=getattr(instance, 'performed_by', None)
             or getattr(instance, 'created_by', None)
             or user,
        notes=notes,
        timestamp=timezone.now(),
    )


# =====================================================
# 🚨 ALERT DISPATCH (ENGINE-DRIVEN)
# =====================================================

def process_alerts(instance):
    """
    Dispatch alerts + escalation via AlertEngine.
    Never raises.
    """
    try:
        AlertEngine.trigger_alert(instance)
        AlertEngine.auto_escalate_unacknowledged(instance)
    except Exception:
        # Alerts must NEVER break core transactions
        pass


# =====================================================
# 📦 INVENTORY TRANSACTIONS (LOCKED + ATOMIC)
# =====================================================

@receiver(post_save, sender=InventoryTransaction)
def inventory_transaction_handler(sender, instance, created, **kwargs):
    if not created:
        return

    with transaction.atomic():
        item = InventoryItem.objects.select_for_update().get(pk=instance.item_id)

        if instance.transaction_type == 'addition':
            InventoryItem.objects.filter(pk=item.pk).update(
                quantity=F('quantity') + instance.quantity
            )

        elif instance.transaction_type == 'removal':
            current_qty = InventoryItem.objects.values_list(
                'quantity', flat=True
            ).get(pk=item.pk)

            if current_qty < instance.quantity:
                raise ValueError(
                    f"Cannot remove {instance.quantity} from {item.name}. "
                    f"Only {current_qty} available."
                )

            InventoryItem.objects.filter(pk=item.pk).update(
                quantity=F('quantity') - instance.quantity
            )

        elif instance.transaction_type == 'adjustment':
            InventoryItem.objects.filter(pk=item.pk).update(
                quantity=Decimal(instance.quantity)
            )

    process_alerts(item)
    create_audit(instance, "created")


@receiver(post_save, sender=InventoryLog)
def inventory_log_handler(sender, instance, created, **kwargs):
    if not created:
        return

    with transaction.atomic():
        item = InventoryItem.objects.select_for_update().get(
            pk=instance.inventory_item_id
        )

        if instance.action == 'added':
            InventoryItem.objects.filter(pk=item.pk).update(
                quantity=F('quantity') + instance.quantity
            )

        elif instance.action == 'removed':
            current_qty = InventoryItem.objects.values_list(
                'quantity', flat=True
            ).get(pk=item.pk)

            if current_qty < instance.quantity:
                raise ValueError(
                    f"Cannot remove {instance.quantity} from {item.name}. "
                    f"Only {current_qty} available."
                )

            InventoryItem.objects.filter(pk=item.pk).update(
                quantity=F('quantity') - instance.quantity
            )

    process_alerts(item)
    create_audit(instance, "created")


# =====================================================
# 🧪 LABORATORY REAGENTS
# =====================================================

@receiver(post_save, sender=LaboratoryReagentLog)
def reagent_log_handler(sender, instance, created, **kwargs):
    if not created:
        return

    with transaction.atomic():
        reagent = LaboratoryReagent.objects.select_for_update().get(
            pk=instance.reagent_id
        )

        if instance.action == 'add':
            LaboratoryReagent.objects.filter(pk=reagent.pk).update(
                quantity=F('quantity') + instance.quantity
            )

        elif instance.action == 'remove':
            current_qty = LaboratoryReagent.objects.values_list(
                'quantity', flat=True
            ).get(pk=reagent.pk)

            if current_qty < instance.quantity:
                raise ValueError(
                    f"Cannot remove {instance.quantity} {reagent.unit} from "
                    f"{reagent.name}. Only {current_qty} available."
                )

            LaboratoryReagent.objects.filter(pk=reagent.pk).update(
                quantity=F('quantity') - instance.quantity
            )

        elif instance.action == 'update':
            LaboratoryReagent.objects.filter(pk=reagent.pk).update(
                quantity=Decimal(instance.quantity)
            )

    process_alerts(reagent)
    create_audit(instance, "created")


# =====================================================
# ⚙️ EQUIPMENT MAINTENANCE & CALIBRATION
# =====================================================

@receiver(post_save, sender=MaintenanceRecord)
def maintenance_record_handler(sender, instance, created, **kwargs):
    if created and instance.equipment:
        instance.equipment.next_maintenance_date = instance.next_due
        instance.equipment.save(update_fields=['next_maintenance_date'])

    process_alerts(instance.equipment)
    create_audit(instance, "created")


@receiver(post_save, sender=CalibrationRecord)
def calibration_record_handler(sender, instance, created, **kwargs):
    if created and instance.equipment:
        instance.equipment.calibration_due_date = instance.next_due
        instance.equipment.save(update_fields=['calibration_due_date'])

    process_alerts(instance.equipment)
    create_audit(instance, "created")


@receiver(post_save, sender=Equipment)
def equipment_handler(sender, instance, created, **kwargs):
    process_alerts(instance)
    create_audit(instance, "created" if created else "updated")


# =====================================================
# 🧠 GENERIC CREATE / DELETE AUDIT BACKSTOP
# =====================================================

@receiver(post_save)
def fallback_audit_post_save(sender, instance, created, **kwargs):
    if sender is AuditLog:
        return

    if not isinstance(instance, AUDIT_MODELS):
        return

    create_audit(
        instance,
        "created" if created else "updated"
    )


@receiver(post_delete)
def fallback_audit_post_delete(sender, instance, **kwargs):
    if sender is AuditLog:
        return

    if not isinstance(instance, AUDIT_MODELS):
        return

    create_audit(instance, "deleted")
