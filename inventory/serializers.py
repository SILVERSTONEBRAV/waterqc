from rest_framework import serializers
from django.utils import timezone
from accounts.models import CustomUser
from sc.models import Shift
from .models import (
    Status, MainCategory, SubCategory, Supplier, ItemType,
    InventoryItem, InventoryTransaction, InventoryLog,
    Equipment, MaintenanceRecord, CalibrationRecord,
    Apparatus, EquipmentStatusLog, ApparatusCondition,
    LaboratoryReagent, LaboratoryReagentLog,
    AlertConfig, AuditLog
)

User = CustomUser

# ======================
# Classification Serializers
# ======================
class StatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Status
        fields = ['id', 'name', 'description']


class MainCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MainCategory
        fields = ['id', 'name', 'description']


class SubCategorySerializer(serializers.ModelSerializer):
    main_category = MainCategorySerializer(read_only=True)

    class Meta:
        model = SubCategory
        fields = ['id', 'name', 'description', 'main_category']


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'phone', 'email', 'address']


class ItemTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemType
        fields = ['id', 'name']


# ======================
# Inventory Serializers
# ======================
class InventoryLogSerializer(serializers.ModelSerializer):
    action_date = serializers.DateTimeField(read_only=True)

    class Meta:
        model = InventoryLog
        fields = ['id', 'inventory_item', 'action', 'quantity', 'action_date', 'notes']


class InventoryItemSerializer(serializers.ModelSerializer):
    supplier = SupplierSerializer(read_only=True)
    item_type = ItemTypeSerializer(read_only=True)
    category = SubCategorySerializer(read_only=True)
    inventory_logs = InventoryLogSerializer(many=True, read_only=True)

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'uuid', 'name', 'item_type', 'category', 'section', 'supplier',
            'purchase_date', 'quantity', 'expiry_date', 'storage_conditions',
            'notes', 'inventory_logs'
        ]


class InventoryTransactionSerializer(serializers.ModelSerializer):
    item = InventoryItemSerializer(read_only=True)
    performed_by = serializers.StringRelatedField(read_only=True)

    item_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryItem.objects.all(), source='item', write_only=True
    )

    class Meta:
        model = InventoryTransaction
        fields = [
            'id', 'item', 'item_id', 'performed_by',
            'transaction_type', 'quantity', 'notes', 'created_at'
        ]
        read_only_fields = ['created_at']

    def create(self, validated_data):
        validated_data['performed_by'] = self.context['request'].user
        return super().create(validated_data)


# ======================
# Laboratory Serializers
# ======================
class LaboratoryReagentLogSerializer(serializers.ModelSerializer):
    performed_by = serializers.StringRelatedField(read_only=True)
    action_date = serializers.DateTimeField(read_only=True)

    class Meta:
        model = LaboratoryReagentLog
        fields = ['id', 'reagent', 'action', 'quantity', 'unit', 'action_date', 'performed_by', 'notes']

    def create(self, validated_data):
        validated_data['performed_by'] = self.context['request'].user
        return super().create(validated_data)


class LaboratoryReagentSerializer(serializers.ModelSerializer):
    supplier = SupplierSerializer(read_only=True)
    item_type = ItemTypeSerializer(read_only=True)
    category = SubCategorySerializer(read_only=True)
    logs = LaboratoryReagentLogSerializer(many=True, required=False)

    class Meta:
        model = LaboratoryReagent
        fields = [
            'id', 'name', 'formula', 'purity', 'section', 'item_type',
            'category', 'supplier', 'purchase_date', 'quantity', 'unit',
            'expiry_date', 'storage_conditions', 'hazard_class', 'msds_file',
            'notes', 'logs'
        ]

    def create(self, validated_data):
        logs_data = validated_data.pop('logs', [])
        reagent = LaboratoryReagent.objects.create(**validated_data)
        user = self.context['request'].user
        for log in logs_data:
            log['performed_by'] = user
            LaboratoryReagentLog.objects.create(reagent=reagent, **log)
        return reagent

    def update(self, instance, validated_data):
        logs_data = validated_data.pop('logs', [])
        user = self.context['request'].user
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        for log in logs_data:
            log['performed_by'] = user
            LaboratoryReagentLog.objects.create(reagent=instance, **log)
        return instance


# ======================
# Equipment & Apparatus Serializers
# ======================
class MaintenanceRecordSerializer(serializers.ModelSerializer):
    performed_by = serializers.StringRelatedField(read_only=True)
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.all(), required=False, allow_null=True)

    class Meta:
        model = MaintenanceRecord
        fields = ['id', 'equipment', 'maintenance_date', 'performed_by', 'details', 'next_due', 'shift']

    def create(self, validated_data):
        user = self.context['request'].user
        equipment = validated_data['equipment']
        validated_data['performed_by'] = user
        if not validated_data.get('shift'):
            validated_data['shift'] = getattr(equipment, 'shift', None)
        if not validated_data.get('next_due'):
            validated_data['next_due'] = validated_data['maintenance_date'] + timezone.timedelta(days=equipment.maintenance_interval)
            equipment.next_maintenance_date = validated_data['next_due']
            equipment.save(update_fields=['next_maintenance_date'])
        return super().create(validated_data)


class CalibrationRecordSerializer(serializers.ModelSerializer):
    calibrated_by = serializers.StringRelatedField(read_only=True)
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.all(), required=False, allow_null=True)

    class Meta:
        model = CalibrationRecord
        fields = ['id', 'equipment', 'calibrated_on', 'calibrated_by', 'next_due', 'notes', 'shift']

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['calibrated_by'] = user
        equipment = validated_data['equipment']
        if not validated_data.get('next_due'):
            validated_data['next_due'] = validated_data['calibrated_on'] + timezone.timedelta(days=equipment.calibration_interval_days)
        return super().create(validated_data)


class EquipmentStatusLogSerializer(serializers.ModelSerializer):
    previous_status = serializers.StringRelatedField(read_only=True)
    new_status = serializers.StringRelatedField(read_only=True)
    changed_by = serializers.StringRelatedField(read_only=True)
    shift = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = EquipmentStatusLog
        fields = ['id', 'equipment', 'previous_status', 'new_status', 'changed_by', 'changed_at', 'notes', 'shift']


class ApparatusConditionSerializer(serializers.ModelSerializer):
    checked_by = serializers.StringRelatedField(read_only=True)
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.all(), required=False, allow_null=True)

    class Meta:
        model = ApparatusCondition
        fields = ['id', 'apparatus', 'status', 'notes', 'checked_by', 'checked_at', 'shift']

    def create(self, validated_data):
        validated_data['checked_by'] = self.context['request'].user
        apparatus = validated_data['apparatus']
        if not validated_data.get('shift'):
            validated_data['shift'] = getattr(apparatus.equipment, 'shift', None)
        return super().create(validated_data)


class ApparatusSerializer(serializers.ModelSerializer):
    conditions = ApparatusConditionSerializer(many=True, required=False)

    class Meta:
        model = Apparatus
        fields = ['id', 'equipment', 'name', 'description', 'conditions']

    def create(self, validated_data):
        conditions_data = validated_data.pop('conditions', [])
        apparatus = Apparatus.objects.create(**validated_data)
        user = self.context['request'].user
        for cond in conditions_data:
            cond['checked_by'] = user
            if not cond.get('shift'):
                cond['shift'] = getattr(apparatus.equipment, 'shift', None)
            ApparatusCondition.objects.create(apparatus=apparatus, **cond)
        return apparatus

    def update(self, instance, validated_data):
        conditions_data = validated_data.pop('conditions', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        user = self.context['request'].user
        for cond in conditions_data:
            cond_id = cond.pop('id', None)
            if cond_id:
                if not cond.get('shift'):
                    cond['shift'] = getattr(instance.equipment, 'shift', None)
                ApparatusCondition.objects.filter(id=cond_id, apparatus=instance).update(**cond, checked_by=user)
            else:
                cond['checked_by'] = user
                if not cond.get('shift'):
                    cond['shift'] = getattr(instance.equipment, 'shift', None)
                ApparatusCondition.objects.create(apparatus=instance, **cond)
        return instance


class EquipmentSerializer(serializers.ModelSerializer):
    main_category = MainCategorySerializer(read_only=True)
    sub_category = SubCategorySerializer(read_only=True)
    supplier = SupplierSerializer(read_only=True)
    status = StatusSerializer(read_only=True)
    maintenance_records = MaintenanceRecordSerializer(many=True, required=False)
    calibration_records = CalibrationRecordSerializer(many=True, required=False)
    apparatuses = ApparatusSerializer(many=True, required=False)
    status_logs = EquipmentStatusLogSerializer(many=True, read_only=True)
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.all(), required=False, allow_null=True)

    class Meta:
        model = Equipment
        fields = [
            'id', 'name', 'description', 'serial_number', 'main_category', 'sub_category',
            'section', 'supplier', 'purchase_date', 'installation_date',
            'last_maintenance_date', 'next_maintenance_date', 'maintenance_interval',
            'calibration_interval_days', 'status', 'quantity', 'expiry_date',
            'storage_conditions', 'inventory_tracking', 'notes',
            'shift', 'maintenance_records', 'calibration_records', 'apparatuses', 'status_logs'
        ]


# ======================
# Alert Serializer
# ======================
class AlertConfigSerializer(serializers.ModelSerializer):
    users_to_notify = serializers.PrimaryKeyRelatedField(many=True, queryset=User.objects.all())

    class Meta:
        model = AlertConfig
        fields = [
            'id', 'name', 'alert_type', 'active', 'threshold_days',
            'min_quantity', 'section', 'users_to_notify', 'created_at', 'updated_at'
        ]


# ======================
# AuditLog Serializer
# ======================
class AuditLogSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    content_object = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ['id', 'content_type', 'object_id', 'content_object', 'action', 'user', 'notes', 'timestamp']

    def get_content_object(self, obj):
        try:
            return str(obj.content_object)
        except Exception:
            return None
