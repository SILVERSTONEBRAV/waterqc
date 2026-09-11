#inventory/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from django.db.models.signals import post_save, post_delete
from .models import (
    Supplier,
    Equipment,
    LaboratoryReagent,
    LaboratoryReagentLog,
    MaintenanceRecord,
    Apparatus,
    LaboratoryGlassware,
    LaboratoryEquipment,
    LaboratoryEquipmentLog,
)
from .signals import log_change  # Your logging automation


# --- Suppliers ---
class SupplierResource(resources.ModelResource):
    class Meta:
        model = Supplier
        fields = ('id', 'name', 'email', 'phone', 'address')
        export_order = ('id', 'name', 'email', 'phone', 'address')

    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        post_save.send(sender=Supplier, instance=instance, created=new)

    def after_delete_instance(self, instance, **kwargs):
        post_delete.send(sender=Supplier, instance=instance)


# --- Equipment ---
class EquipmentResource(resources.ModelResource):
    supplier = fields.Field(
        column_name='supplier',
        attribute='supplier',
        widget=ForeignKeyWidget(Supplier, field='name')
    )

    class Meta:
        model = Equipment
        fields = ('id', 'name', 'description', 'status', 'supplier')
        export_order = ('id', 'name', 'description', 'status', 'supplier')

    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        post_save.send(sender=Equipment, instance=instance, created=new)

    def after_delete_instance(self, instance, **kwargs):
        post_delete.send(sender=Equipment, instance=instance)


# --- Laboratory Reagent ---
class LaboratoryReagentResource(resources.ModelResource):
    class Meta:
        model = LaboratoryReagent
        fields = ('id', 'name', 'quantity', 'unit', 'expiry_date')
        export_order = ('id', 'name', 'quantity', 'unit', 'expiry_date')

    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        post_save.send(sender=LaboratoryReagent, instance=instance, created=new)

    def after_delete_instance(self, instance, **kwargs):
        post_delete.send(sender=LaboratoryReagent, instance=instance)


# --- Laboratory Reagent Log ---
class LaboratoryReagentLogResource(resources.ModelResource):
    reagent = fields.Field(
        column_name='reagent',
        attribute='reagent',
        widget=ForeignKeyWidget(LaboratoryReagent, field='name')
    )

    class Meta:
        model = LaboratoryReagentLog
        fields = ('id', 'reagent', 'quantity', 'unit', 'action', 'action_date')
        export_order = ('id', 'reagent', 'quantity', 'unit', 'action', 'action_date')

    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        post_save.send(sender=LaboratoryReagentLog, instance=instance, created=new)

    def after_delete_instance(self, instance, **kwargs):
        post_delete.send(sender=LaboratoryReagentLog, instance=instance)


# --- Maintenance Record ---
class MaintenanceRecordResource(resources.ModelResource):
    equipment = fields.Field(
        column_name='equipment',
        attribute='equipment',
        widget=ForeignKeyWidget(Equipment, field='name')
    )

    class Meta:
        model = MaintenanceRecord
        fields = ('id', 'equipment', 'details', 'performed_by', 'performed_at')
        export_order = ('id', 'equipment', 'details', 'performed_by', 'performed_at')

    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        post_save.send(sender=MaintenanceRecord, instance=instance, created=new)

    def after_delete_instance(self, instance, **kwargs):
        post_delete.send(sender=MaintenanceRecord, instance=instance)


# --- Apparatus ---
class ApparatusResource(resources.ModelResource):
    class Meta:
        model = Apparatus
        fields = ('id', 'name', 'description', 'status')
        export_order = ('id', 'name', 'description', 'status')

    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        post_save.send(sender=Apparatus, instance=instance, created=new)

    def after_delete_instance(self, instance, **kwargs):
        post_delete.send(sender=Apparatus, instance=instance)


# --- Laboratory Glassware ---
class LaboratoryGlasswareResource(resources.ModelResource):
    class Meta:
        model = LaboratoryGlassware
        fields = ('id', 'name', 'description', 'status')
        export_order = ('id', 'name', 'description', 'status')

    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        post_save.send(sender=LaboratoryGlassware, instance=instance, created=new)

    def after_delete_instance(self, instance, **kwargs):
        post_delete.send(sender=LaboratoryGlassware, instance=instance)


# --- Laboratory Equipment ---
class LaboratoryEquipmentResource(resources.ModelResource):
    class Meta:
        model = LaboratoryEquipment
        fields = ('id', 'name', 'description', 'status')
        export_order = ('id', 'name', 'description', 'status')

    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        post_save.send(sender=LaboratoryEquipment, instance=instance, created=new)

    def after_delete_instance(self, instance, **kwargs):
        post_delete.send(sender=LaboratoryEquipment, instance=instance)


# --- Laboratory Equipment Log ---
class LaboratoryEquipmentLogResource(resources.ModelResource):
    equipment = fields.Field(
        column_name='equipment',
        attribute='equipment',
        widget=ForeignKeyWidget(LaboratoryEquipment, field='name')
    )

    class Meta:
        model = LaboratoryEquipmentLog
        fields = ('id', 'equipment', 'status', 'logged_at')
        export_order = ('id', 'equipment', 'status', 'logged_at')

    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        post_save.send(sender=LaboratoryEquipmentLog, instance=instance, created=new)

    def after_delete_instance(self, instance, **kwargs):
        post_delete.send(sender=LaboratoryEquipmentLog, instance=instance)
