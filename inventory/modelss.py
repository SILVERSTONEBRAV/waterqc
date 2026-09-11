#inventory/models.py

import random
import string
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.db import models
from accounts.models import CustomUser

User = CustomUser

def generate_uuid(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


# ======================
# Core Classification Models
# ======================

class Status(models.Model):
    """Represents the condition or availability status of an inventory item."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Statuses"

    def __str__(self):
        return self.name


class MainCategory(models.Model):
    """Top-level category for grouping equipment and inventory."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    """Subcategory under a main category."""
    main_category = models.ForeignKey(MainCategory, related_name='subcategories', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('main_category', 'name')

    def __str__(self):
        return f"{self.name} ({self.main_category.name})"


class Supplier(models.Model):
    name = models.CharField(max_length=100, unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class ItemType(models.Model):
    """Type of inventory item (e.g., consumable, tool)."""
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


# ======================
# ALERT CONFIGURATION
# ======================

class AlertConfig(models.Model):
    """Configurable alerts for inventory, equipment, or laboratory reagents."""
    ALERT_TYPE_CHOICES = [
        ('restock', 'Low Stock / Restock'),
        ('maintenance_due', 'Equipment Maintenance Due'),
        ('calibration_due', 'Equipment Calibration Due'),
        ('expiry', 'Reagent Expiry'),
        ('custom', 'Custom Alert'),
    ]

    name = models.CharField(max_length=100, unique=True)
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPE_CHOICES)
    active = models.BooleanField(default=True)
    threshold_days = models.PositiveIntegerField(default=7)
    min_quantity = models.PositiveIntegerField(null=True, blank=True)
    section = models.CharField(max_length=50, blank=True, null=True)
    users_to_notify = models.ManyToManyField(User, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['alert_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.alert_type})"

    def is_triggered_for(self, item):
        today = timezone.now().date()
        if self.alert_type == 'restock' and hasattr(item, 'quantity'):
            min_qty = self.min_quantity or 1
            return item.quantity < min_qty
        if self.alert_type == 'maintenance_due' and hasattr(item, 'next_maintenance_date'):
            if item.next_maintenance_date:
                return (item.next_maintenance_date - today).days <= self.threshold_days
        if self.alert_type == 'calibration_due' and hasattr(item, 'calibration_due_date'):
            if item.calibration_due_date:
                return (item.calibration_due_date - today).days <= self.threshold_days
        if self.alert_type == 'expiry' and hasattr(item, 'expiry_date'):
            if item.expiry_date:
                return (item.expiry_date - today).days <= self.threshold_days
        return False

    def send_alert(self, item, message=None):
        from .signals import send_alert  # avoid circular import
        msg = message or f"{self.alert_type} triggered for {item}"
        send_alert(self, item, msg)


# ======================
# Inventory Transactions
# ======================
class InventoryItem(models.Model):
    SECTION_CHOICES = CustomUser.SECTION_CHOICES

    name = models.CharField(max_length=100)
    item_type = models.ForeignKey(ItemType, related_name='inventory_items', on_delete=models.CASCADE)
    category = models.ForeignKey(SubCategory, related_name='inventory_items', on_delete=models.CASCADE)
    section = models.CharField(max_length=50, choices=SECTION_CHOICES)
    supplier = models.ForeignKey(Supplier, related_name='inventory_items', on_delete=models.SET_NULL, null=True, blank=True)
    purchase_date = models.DateField()
    quantity = models.PositiveIntegerField()
    expiry_date = models.DateField(blank=True, null=True)
    storage_conditions = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.section})"


class InventoryTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('addition', 'Addition'),
        ('removal', 'Removal'),
        ('adjustment', 'Adjustment'),
    ]

    item = models.ForeignKey(InventoryItem, related_name='transactions', on_delete=models.CASCADE)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    transaction_type = models.CharField(max_length=50, choices=TRANSACTION_TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.item.name} - {self.get_transaction_type_display()} - {self.quantity}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new:
            item = self.item
            if self.transaction_type == 'addition':
                item.quantity += self.quantity
            elif self.transaction_type == 'removal':
                if item.quantity >= self.quantity:
                    item.quantity -= self.quantity
                else:
                    raise ValueError(
                        f"Cannot remove {self.quantity} from {item.name}. Only {item.quantity} available."
                    )
            elif self.transaction_type == 'adjustment':
                item.quantity = self.quantity  # override current quantity
            item.save(update_fields=['quantity'])
        super().save(*args, **kwargs)




## ======================
# Equipment (Standalone)
# ======================
class Equipment(models.Model):
    SECTION_CHOICES = CustomUser.SECTION_CHOICES

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    serial_number = models.CharField(max_length=255, blank=True, null=True)
    main_category = models.ForeignKey(MainCategory, related_name='equipment', on_delete=models.CASCADE)
    sub_category = models.ForeignKey(SubCategory, related_name='equipment', on_delete=models.CASCADE)
    section = models.CharField(max_length=50, choices=SECTION_CHOICES)
    supplier = models.ForeignKey(Supplier, related_name='equipment', on_delete=models.SET_NULL, null=True, blank=True)
    purchase_date = models.DateField(blank=True, null=True)
    installation_date = models.DateField(blank=True, null=True)
    last_maintenance_date = models.DateField(blank=True, null=True)
    next_maintenance_date = models.DateField(blank=True, null=True, editable=False)
    maintenance_interval = models.PositiveIntegerField(default=180)
    calibration_interval_days = models.PositiveIntegerField(default=180)
    status = models.ForeignKey(Status, related_name='equipment', on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    expiry_date = models.DateField(blank=True, null=True)
    storage_conditions = models.TextField(blank=True, null=True)
    inventory_tracking = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.last_maintenance_date:
            self.next_maintenance_date = self.last_maintenance_date + timezone.timedelta(days=self.maintenance_interval)
        super().save(*args, **kwargs)


class MaintenanceRecord(models.Model):
    equipment = models.ForeignKey(Equipment, related_name='maintenance_records', on_delete=models.CASCADE)
    maintenance_date = models.DateField()
    performed_by = models.CharField(max_length=100)
    details = models.TextField()
    next_due = models.DateField(blank=True, null=True)  # computed automatically

    class Meta:
        ordering = ['-maintenance_date']

    def __str__(self):
        return f"{self.equipment.name} maintenance on {self.maintenance_date}"

    def save(self, *args, **kwargs):
        if self.equipment and self.maintenance_date:
            self.next_due = self.maintenance_date + timezone.timedelta(days=self.equipment.maintenance_interval)
            self.equipment.next_maintenance_date = self.next_due
            self.equipment.save(update_fields=['next_maintenance_date'])
        super().save(*args, **kwargs)


class CalibrationRecord(models.Model):
    equipment = models.ForeignKey(Equipment, related_name='calibration_records', on_delete=models.CASCADE)
    calibrated_on = models.DateField()
    calibrated_by = models.CharField(max_length=100)
    next_due = models.DateField(blank=True, null=True)  # computed automatically
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-calibrated_on']

    def __str__(self):
        return f"{self.equipment.name} calibrated on {self.calibrated_on}"

    def save(self, *args, **kwargs):
        if self.equipment and self.calibrated_on:
            self.next_due = self.calibrated_on + timezone.timedelta(days=self.equipment.calibration_interval_days)
        super().save(*args, **kwargs)

# ======================
# Apparatus & Condition Tracking
# ======================

class Apparatus(models.Model):
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="apparatuses")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.equipment.name})"


class EquipmentStatusLog(models.Model):
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="status_logs")
    previous_status = models.ForeignKey(Status, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    new_status = models.ForeignKey(Status, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    shift = models.ForeignKey('sc.Shift', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='equipment_status_logs')

    class Meta:
        ordering = ['-changed_at']


class ApparatusCondition(models.Model):
    apparatus = models.ForeignKey(Apparatus, on_delete=models.CASCADE, related_name="conditions")
    status = models.ForeignKey(Status, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    checked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    checked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-checked_at']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        equipment = self.apparatus.equipment
        previous_status = equipment.status
        if self.status and previous_status != self.status:
            equipment.status = self.status
            equipment.save(update_fields=["status"])
            EquipmentStatusLog.objects.create(
                equipment=equipment,
                previous_status=previous_status,
                new_status=self.status,
                changed_by=self.checked_by,
                notes=self.notes
            )

    def __str__(self):
        return f"{self.apparatus.name} condition on {self.checked_at}"


# ======================
# Inventory Models
# ======================



class InventoryLog(models.Model):
    inventory_item = models.ForeignKey(InventoryItem, related_name='inventory_logs', on_delete=models.CASCADE)
    action = models.CharField(max_length=50, choices=[('added','Added'),('removed','Removed'),('updated','Updated')])
    quantity = models.PositiveIntegerField()
    action_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-action_date']

    def __str__(self):
        return f"{self.inventory_item.name} - {self.get_action_display()} - {self.quantity} on {self.action_date:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new:
            item = self.inventory_item
            if self.action == 'added':
                item.quantity += self.quantity
            elif self.action == 'removed':
                if item.quantity >= self.quantity:
                    item.quantity -= self.quantity
                else:
                    raise ValueError(f"Cannot remove {self.quantity} from {item.name}. Only {item.quantity} in stock.")
            item.save(update_fields=['quantity'])
        super().save(*args, **kwargs)


# ======================
# Laboratory Reagent Models
# ======================

class LaboratoryReagent(models.Model):
    SECTION_CHOICES = CustomUser.SECTION_CHOICES
    HAZARD_CHOICES = [
        ('flammable', 'Flammable'),
        ('toxic', 'Toxic'),
        ('corrosive', 'Corrosive'),
        ('oxidizer', 'Oxidizer'),
        ('environmental', 'Environmental Hazard'),
        ('irritant', 'Irritant'),
        ('none', 'None'),
    ]

    name = models.CharField(max_length=100)
    formula = models.CharField(max_length=100, blank=True, null=True)
    purity = models.CharField(max_length=50, blank=True, null=True)
    section = models.CharField(max_length=50, choices=SECTION_CHOICES)
    item_type = models.ForeignKey(ItemType, on_delete=models.CASCADE, related_name='laboratory_reagents')
    category = models.ForeignKey(SubCategory, on_delete=models.CASCADE, related_name='laboratory_reagents')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='laboratory_reagents')
    purchase_date = models.DateField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20, default='g')
    expiry_date = models.DateField(blank=True, null=True)
    storage_conditions = models.TextField(blank=True, null=True)
    hazard_class = models.CharField(max_length=50, choices=HAZARD_CHOICES, default='none')
    msds_file = models.FileField(upload_to='laboratory/msds/', blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.section})"

class LaboratoryGlassware(models.Model):
    """Represents laboratory glassware items such as beakers, flasks, pipettes."""
    SECTION_CHOICES = CustomUser.SECTION_CHOICES

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    capacity_ml = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    section = models.CharField(max_length=50, choices=SECTION_CHOICES)
    quantity = models.PositiveIntegerField(default=1)
    condition = models.ForeignKey(Status, on_delete=models.SET_NULL, null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    purchase_date = models.DateField(blank=True, null=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='glassware')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="glassware_created")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="glassware_updated")
    shift = models.ForeignKey('sc.Shift', on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Laboratory Glassware"
        verbose_name_plural = "Laboratory Glassware"
        ordering = ['name']

    def __str__(self):
        cap_str = f" ({self.capacity_ml} ml)" if self.capacity_ml else ""
        return f"{self.name}{cap_str}"



class LaboratoryReagentLog(models.Model):
    reagent = models.ForeignKey(LaboratoryReagent, related_name='logs', on_delete=models.CASCADE)
    action = models.CharField(max_length=50, choices=[('added','Added'),('removed','Removed'),('updated','Updated')])
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20, blank=True, null=True)
    action_date = models.DateTimeField(auto_now_add=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-action_date']

    def __str__(self):
        return f"{self.reagent.name} - {self.get_action_display()} - {self.quantity} on {self.action_date:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new:
            reagent = self.reagent
            if self.action == 'added':
                reagent.quantity += self.quantity
            elif self.action == 'removed':
                if reagent.quantity >= self.quantity:
                    reagent.quantity -= self.quantity
                else:
                    raise ValueError(
                        f"Cannot remove {self.quantity} {reagent.unit} from {reagent.name}. Only {reagent.quantity} available."
                    )
            reagent.save(update_fields=['quantity'])
        super().save(*args, **kwargs)



class AuditLog(models.Model):
    """Automated audit log for all models with system/user tracking."""

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name='inventory_auditlogs'  # <--- unique per app
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    action = models.CharField(max_length=50)  # e.g., 'created', 'updated', 'deleted', 'alert_triggered'
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        return f"{self.action} - {self.content_type.model} ({self.object_id}) at {self.timestamp:%Y-%m-%d %H:%M}"
# ======================