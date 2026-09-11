from rest_framework import serializers
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import datetime

from t.models import TreatmentPlant, TreatmentPlantPhase
from ca.models import Chemical
from o.models import ChemicalTank
from accounts.models import CustomUser
from .models import XmicalConcentration


# ===============================
# 🔁 Reusable Mini Serializers
# ===============================
class TreatmentPlantSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreatmentPlant
        fields = ['id', 'name']


class ChemicalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chemical
        fields = ['id', 'name', 'unit', 'hydrometer_formula']


class ChemicalTankSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChemicalTank
        fields = ['id', 'name', 'volume_liters']


class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'full_name', 'email']


# ===============================
# 🔤 Base Serializer
# ===============================
class XmicalConcentrationBaseSerializer(serializers.ModelSerializer):
    treatment_plant = serializers.PrimaryKeyRelatedField(queryset=TreatmentPlant.objects.all())
    phase = serializers.PrimaryKeyRelatedField(
        queryset=TreatmentPlantPhase.objects.all(),
        required=False, allow_null=True
    )
    chemical = serializers.PrimaryKeyRelatedField(queryset=Chemical.objects.all())
    tank = serializers.PrimaryKeyRelatedField(queryset=ChemicalTank.objects.all())
    measured_by = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        required=False, allow_null=True
    )

    hydrometer_reading = serializers.DecimalField(
        max_digits=8, decimal_places=3, min_value=Decimal('0.001'),
        error_messages={"min_value": "Reading must be greater than zero."}
    )

    class Meta:
        model = XmicalConcentration
        fields = '__all__'
        read_only_fields = [
            'id', 'chemical_name', 'concentration_mg_per_l',
            'formula_used', 'created_at', 'updated_at',
            'created_by', 'updated_by'
        ]

    def validate_measurement_date(self, value):
        if isinstance(value, str):
            parsed = parse_datetime(value)
            if not parsed:
                raise serializers.ValidationError(
                    "Invalid datetime format. Use ISO 8601 with timezone (e.g., 2025-07-08T14:00:00+03:00)."
                )
            return parsed
        elif isinstance(value, datetime.datetime):
            return value
        raise serializers.ValidationError("measurement_date must be a string or datetime object.")

    def validate(self, data):
        chemical = data.get("chemical")
        if not chemical or not chemical.hydrometer_formula:
            raise serializers.ValidationError({
                "chemical": f"No hydrometer formula is defined for {chemical.name if chemical else 'this chemical'}."
            })
        return data


# ===============================
# 🆕 Create Serializer
# ===============================
class XmicalConcentrationCreateSerializer(XmicalConcentrationBaseSerializer):
    def validate(self, data):
        data = super().validate(data)

        chemical = data.get("chemical")
        tank = data.get("tank")
        measurement_date = data.get("measurement_date")

        if chemical and tank and measurement_date:
            exists = XmicalConcentration.objects.filter(
                chemical=chemical,
                tank=tank,
                measurement_date=measurement_date
            ).exists()
            if exists:
                raise serializers.ValidationError(
                    "A measurement already exists for this chemical, tank, and date."
                )

        return data

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        validated_data.setdefault("measurement_date", timezone.now())
        chemical = validated_data.pop('chemical')

        instance = XmicalConcentration(
            **validated_data,
            chemical=chemical,
            chemical_name=chemical.name,
            created_by=user if user and user.is_authenticated else None,
            updated_by=user if user and user.is_authenticated else None,
        )
        instance.save()
        return instance


# ===============================
# 🆙 Update Serializer
# ===============================
class XmicalConcentrationUpdateSerializer(XmicalConcentrationBaseSerializer):
    def update(self, instance, validated_data):
        user = self.context.get("request").user

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.updated_by = user if user and user.is_authenticated else None

        # Force recalculation
        result, formula = instance.calculate_concentration()
        instance.concentration_mg_per_l = result
        instance.formula_used = formula

        instance.save()
        return instance


# ===============================
# 📄 Detail Serializer (Read-only)
# ===============================
class XmicalConcentrationDetailSerializer(serializers.ModelSerializer):
    treatment_plant = TreatmentPlantSerializer(read_only=True)
    phase = serializers.StringRelatedField(read_only=True)
    chemical = ChemicalSerializer(read_only=True)
    tank = ChemicalTankSerializer(read_only=True)
    measured_by = UserMiniSerializer(read_only=True)
    created_by = UserMiniSerializer(read_only=True)
    updated_by = UserMiniSerializer(read_only=True)

    label = serializers.CharField(source='label', read_only=True)
    is_recent = serializers.BooleanField(read_only=True)

    class Meta:
        model = XmicalConcentration
        fields = [
            'id', 'label', 'treatment_plant', 'phase', 'chemical',
            'chemical_name', 'tank', 'measured_by', 'measurement_date',
            'hydrometer_reading', 'concentration_mg_per_l', 'formula_used',
            'comments', 'created_at', 'updated_at', 'created_by', 'updated_by',
            'is_recent'
        ]


# ===============================
# 📋 List Serializer (Slim)
# ===============================
class XmicalConcentrationListSerializer(serializers.ModelSerializer):
    chemical_name = serializers.CharField()
    concentration = serializers.DecimalField(
        source="concentration_mg_per_l", max_digits=8, decimal_places=3, read_only=True
    )
    treatment_plant = serializers.StringRelatedField()
    tank = serializers.StringRelatedField()
    measured_by = serializers.StringRelatedField()
    formatted_concentration = serializers.SerializerMethodField()

    def get_formatted_concentration(self, obj):
        unit = getattr(obj.chemical, 'unit', 'mg/L') if hasattr(obj, 'chemical') else 'mg/L'
        if obj.concentration_mg_per_l is None:
            return "-"
        return f"{obj.concentration_mg_per_l:.3f} {unit}"

    class Meta:
        model = XmicalConcentration
        fields = [
            'id', 'chemical_name', 'concentration', 'formatted_concentration',
            'treatment_plant', 'tank', 'measured_by', 'measurement_date'
        ]
