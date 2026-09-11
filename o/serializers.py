from rest_framework import serializers
from django.utils.timezone import now
from .models import *
from accounts.models import CustomUser
from ca.models import Chemical
from t.models import TreatmentPlant, TreatmentPlantPhase
from sc.models import ShiftAssignment


class MonitoringTimeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitoringTime
        fields = ['id', 'time']
        read_only_fields = ['id', 'time']


class ChemicalCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChemicalCategory
        fields = ['id', 'chemical', 'category']


class ChemicalPumpListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChemicalPump
        fields = ['id', 'name', 'phase', 'category']


class ChemicalPumpDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChemicalPump
        fields = '__all__'

    def validate_category(self, value):
        if value not in ChemicalCategory.Category.values:
            raise serializers.ValidationError("Invalid chemical category.")
        return value


class PumpStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = PumpStatus
        fields = '__all__'

    def validate_status(self, value):
        if value not in PumpStatus.Status.values:
            raise serializers.ValidationError("Invalid pump status.")
        return value


class ChemicalTankListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChemicalTank
        fields = ['id', 'name', 'phase', 'capacity_liters', 'category']


class ChemicalTankDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChemicalTank
        fields = '__all__'

    def validate_capacity_liters(self, value):
        if value <= 0:
            raise serializers.ValidationError("Capacity must be greater than 0.")
        return value


class BaseUsageFields:
    treatment_plant = serializers.PrimaryKeyRelatedField(queryset=TreatmentPlant.objects.all())
    phase = serializers.PrimaryKeyRelatedField(queryset=TreatmentPlantPhase.objects.all())
    pump_used = serializers.PrimaryKeyRelatedField(queryset=ChemicalPump.objects.all(), allow_null=True)
    tank_used = serializers.PrimaryKeyRelatedField(queryset=ChemicalTank.objects.all(), allow_null=True)
    monitoring_time = serializers.PrimaryKeyRelatedField(queryset=MonitoringTime.objects.all())
    recorded_by = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), required=False)
    shift_assignment = serializers.PrimaryKeyRelatedField(queryset=ShiftAssignment.objects.all(), required=False, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True)

    def validate_raw_water_flow_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError("Flow rate must be greater than zero.")
        return value

    def validate_actual_dosage(self, value):
        if value < 0:
            raise serializers.ValidationError("Actual dosage cannot be negative.")
        return value


class CoagulantUsageRecordListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoagulantUsageRecord
        fields = ['id', 'chemical', 'actual_dosage', 'date', 'monitoring_time']


class CoagulantUsageRecordDetailSerializer(serializers.ModelSerializer, BaseUsageFields):
    chemical = serializers.PrimaryKeyRelatedField(queryset=Chemical.objects.filter(categories__category='Coagulant'))

    class Meta:
        model = CoagulantUsageRecord
        fields = '__all__'


class PHAdjusterUsageRecordListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PHAdjusterUsageRecord
        fields = ['id', 'chemical', 'actual_dosage', 'date', 'monitoring_time']


class PHAdjusterUsageRecordDetailSerializer(serializers.ModelSerializer, BaseUsageFields):
    chemical = serializers.PrimaryKeyRelatedField(queryset=Chemical.objects.filter(categories__category='PH Adjuster'))

    class Meta:
        model = PHAdjusterUsageRecord
        fields = '__all__'


class DisinfectantUsageRecordListSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisinfectantUsageRecord
        fields = ['id', 'chemical', 'actual_reading', 'date', 'monitoring_time']


class DisinfectantUsageRecordDetailSerializer(serializers.ModelSerializer, BaseUsageFields):
    chemical = serializers.PrimaryKeyRelatedField(queryset=Chemical.objects.filter(categories__category='Disinfectant'))

    class Meta:
        model = DisinfectantUsageRecord
        fields = '__all__'

    def validate_actual_reading(self, value):
        if value < 0:
            raise serializers.ValidationError("Actual reading must be non-negative.")
        return value


class FlocculantUsageRecordListSerializer(serializers.ModelSerializer):
    class Meta:
        model = FlocculantUsageRecord
        fields = ['id', 'chemical', 'quantity_used_kg', 'date', 'monitoring_time']


class FlocculantUsageRecordDetailSerializer(serializers.ModelSerializer, BaseUsageFields):
    chemical = serializers.PrimaryKeyRelatedField(queryset=Chemical.objects.filter(categories__category='Flocculant'))

    class Meta:
        model = FlocculantUsageRecord
        fields = '__all__'

    def validate_quantity_used_kg(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity used must be non-negative.")
        return value


class ChemicalUsageRecordSerializer(serializers.ModelSerializer):
    treatment_plant = serializers.PrimaryKeyRelatedField(queryset=TreatmentPlant.objects.all())
    chemical = serializers.PrimaryKeyRelatedField(queryset=Chemical.objects.all())
    recorded_by = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), required=False)

    class Meta:
        model = ChemicalUsageRecord
        fields = '__all__'

    def validate_quantity_used_kg(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity used must be non-negative.")
        return value


class ReservoirListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservoir
        fields = ['id', 'name', 'phase', 'length_m', 'width_m', 'depth_m']


class ReservoirDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservoir
        fields = '__all__'

    def validate(self, data):
        for field in ['length_m', 'width_m', 'depth_m']:
            if data.get(field, 1) <= 0:
                raise serializers.ValidationError(f"{field} must be greater than 0.")
        return data


class ReservoirLevelSerializer(serializers.ModelSerializer):
    reservoir = serializers.PrimaryKeyRelatedField(queryset=Reservoir.objects.all())
    monitoring_time = serializers.PrimaryKeyRelatedField(queryset=MonitoringTime.objects.all())

    class Meta:
        model = ReservoirLevel
        fields = '__all__'

    def validate_level_m(self, value):
        if value < 0:
            raise serializers.ValidationError("Water level must be non-negative.")
        return value
