
from rest_framework import serializers
from django.utils import timezone
from .models import (
    ChemicalCategory, ChemicalPump, PumpStatus, ChemicalTank,
    CoagulantUsageRecord, PHAdjusterUsageRecord, DisinfectantUsageRecord,
    ChemicalUsageRecord, Reservoir, ReservoirLevel,
    MonitoringTime
)
from t.models import TreatmentPlantPhase
from ca.models import Chemical
from sc.models import ShiftAssignment
from t.serializers import TreatmentPlantPhaseSerializer


# ========== Nested Serializers ==========

class TreatmentPlantPhaseNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreatmentPlantPhase
        fields = ['id', 'name', 'treatment_plant']


class ChemicalNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chemical
        fields = ['id', 'name']


# ========== Infrastructure ==========

class ChemicalCategorySerializer(serializers.ModelSerializer):
    chemical = ChemicalNestedSerializer(read_only=True)

    class Meta:
        model = ChemicalCategory
        fields = '__all__'


class ChemicalPumpSerializer(serializers.ModelSerializer):
    phase = TreatmentPlantPhaseNestedSerializer(read_only=True)

    class Meta:
        model = ChemicalPump
        fields = '__all__'


class ChemicalPumpWritableSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChemicalPump
        fields = '__all__'


class ChemicalTankSerializer(serializers.ModelSerializer):
    phase = TreatmentPlantPhaseNestedSerializer(read_only=True)

    class Meta:
        model = ChemicalTank
        fields = '__all__'


class ChemicalTankWritableSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChemicalTank
        fields = '__all__'


# ========== Usage Records ==========

class CoagulantUsageRecordSerializer(serializers.ModelSerializer):
    chemical = ChemicalNestedSerializer(read_only=True)

    class Meta:
        model = CoagulantUsageRecord
        fields = '__all__'


class PHAdjusterUsageRecordSerializer(serializers.ModelSerializer):
    chemical = ChemicalNestedSerializer(read_only=True)

    class Meta:
        model = PHAdjusterUsageRecord
        fields = '__all__'


class DisinfectantUsageRecordSerializer(serializers.ModelSerializer):
    chemical = ChemicalNestedSerializer(read_only=True)

    class Meta:
        model = DisinfectantUsageRecord
        fields = '__all__'


# ========== Reservoir ==========

class ReservoirSerializer(serializers.ModelSerializer):
    phase = TreatmentPlantPhaseNestedSerializer(read_only=True)

    class Meta:
        model = Reservoir
        fields = '__all__'


class ReservoirLevelSerializer(serializers.ModelSerializer):
    reservoir = ReservoirSerializer(read_only=True)

    class Meta:
        model = ReservoirLevel
        fields = '__all__'


# ========== Chemical Usage Summary ==========

class ChemicalUsageRecordSerializer(serializers.ModelSerializer):
    chemical = ChemicalNestedSerializer(read_only=True)

    class Meta:
        model = ChemicalUsageRecord
        fields = '__all__'


# ========== Monitoring Time ==========

class MonitoringTimeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitoringTime
        fields = '__all__'
