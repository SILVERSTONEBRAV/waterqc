from rest_framework import serializers
from .models import (
    OperationStatus,
    PhaseLossRate,
    Backwashing,
    Disludging,
    PumpFlush
)


class OperationStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationStatus
        fields = ['id', 'name']


class PhaseLossRateSerializer(serializers.ModelSerializer):
    phase_name = serializers.StringRelatedField(source='phase', read_only=True)

    class Meta:
        model = PhaseLossRate
        fields = [
            'id',
            'phase',
            'phase_name',
            'operation',
            'loss_rate_m3pm',
            'effective_date'
        ]
        extra_kwargs = {
            'loss_rate_m3pm': {'required': True}
        }


class BackwashingSerializer(serializers.ModelSerializer):
    phase_name = serializers.StringRelatedField(source='phase', read_only=True)
    filter_unit_name = serializers.StringRelatedField(source='filter_unit', read_only=True)
    performed_by_name = serializers.StringRelatedField(source='performed_by', read_only=True)
    shift_assignment_info = serializers.StringRelatedField(source='shift_assignment', read_only=True)
    status_display = serializers.StringRelatedField(source='status', read_only=True)

    class Meta:
        model = Backwashing
        fields = [
            'id',
            'treatment_plant',
            'phase',
            'phase_name',
            'filter_unit',
            'filter_unit_name',
            'performed_by',
            'performed_by_name',
            'shift_assignment',
            'shift_assignment_info',
            'start_time',
            'end_time',
            'duration_minutes',
            'water_lost_m3',
            'remarks',
            'status',
            'status_display',
            'created_at',
            'updated_at'
        ]


class DisludgingSerializer(serializers.ModelSerializer):
    phase_name = serializers.StringRelatedField(source='phase', read_only=True)
    clarifier_name = serializers.StringRelatedField(source='clarifier', read_only=True)
    performed_by_name = serializers.StringRelatedField(source='performed_by', read_only=True)
    shift_assignment_info = serializers.StringRelatedField(source='shift_assignment', read_only=True)
    status_display = serializers.StringRelatedField(source='status', read_only=True)

    class Meta:
        model = Disludging
        fields = [
            'id',
            'treatment_plant',
            'phase',
            'phase_name',
            'clarifier',
            'clarifier_name',
            'performed_by',
            'performed_by_name',
            'shift_assignment',
            'shift_assignment_info',
            'start_time',
            'end_time',
            'duration_minutes',
            'water_lost_m3',
            'remarks',
            'status',
            'status_display',
            'created_at',
            'updated_at'
        ]


class PumpFlushSerializer(serializers.ModelSerializer):
    phase_name = serializers.StringRelatedField(source='phase', read_only=True)
    chemical_pump_name = serializers.StringRelatedField(source='chemical_pump', read_only=True)
    performed_by_name = serializers.StringRelatedField(source='performed_by', read_only=True)
    shift_assignment_info = serializers.StringRelatedField(source='shift_assignment', read_only=True)
    status_display = serializers.StringRelatedField(source='status', read_only=True)

    class Meta:
        model = PumpFlush
        fields = [
            'id',
            'treatment_plant',
            'phase',
            'phase_name',
            'chemical_pump',
            'chemical_pump_name',
            'performed_by',
            'performed_by_name',
            'shift_assignment',
            'shift_assignment_info',
            'start_time',
            'end_time',
            'duration_minutes',
            'water_lost_m3',
            'remarks',
            'status',
            'status_display',
            'created_at',
            'updated_at'
        ]
