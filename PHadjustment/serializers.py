from rest_framework import serializers
from decimal import Decimal
from django.core.exceptions import ValidationError

from accounts.models import CustomUser
from t.models import TreatmentPlant
from .models import PHAdjustmentTest, PHAdjustmentJarResult


# ===========================================
# ✅ Mini Serializers
# ===========================================
class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'full_name', 'email']


class TreatmentPlantMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreatmentPlant
        fields = ['id', 'name']


# ===========================================
# ✅ Jar Result Serializer
# ===========================================
class PHAdjustmentJarResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = PHAdjustmentJarResult
        exclude = ['test']
        read_only_fields = ['performance_rank', 'is_optimal', 'created_at']

    def validate(self, data):
        for ph_field in ['initial_ph', 'final_ph']:
            value = data.get(ph_field)
            if value is not None and (value < 0 or value > 14):
                raise serializers.ValidationError({ph_field: "pH must be between 0 and 14."})
        return data


# ===========================================
# ✅ Read-only Detail Serializer
# ===========================================
class PHAdjustmentTestDetailSerializer(serializers.ModelSerializer):
    treatment_plant = TreatmentPlantMiniSerializer(read_only=True)
    analyst = UserMiniSerializer(read_only=True)

    jar_results = PHAdjustmentJarResultSerializer(many=True, read_only=True)

    verified_by = UserMiniSerializer(read_only=True)
    confirmed_by = UserMiniSerializer(read_only=True)
    approved_by = UserMiniSerializer(read_only=True)

    class Meta:
        model = PHAdjustmentTest
        fields = '__all__'


# ===========================================
# ✅ Create/Update Serializer (Nested Input)
# ===========================================
class PHAdjustmentTestWriteSerializer(serializers.ModelSerializer):
    jar_results = PHAdjustmentJarResultSerializer(many=True, write_only=True)

    class Meta:
        model = PHAdjustmentTest
        exclude = ['verified_by', 'verified_at', 'confirmed_by', 'confirmed_at',
                   'approved_by', 'approved_at', 'needs_review', 'created_at']
        read_only_fields = ['established_dosage_mg_per_l']

    def create(self, validated_data):
        jar_data = validated_data.pop('jar_results', [])
        user = self.context['request'].user if self.context.get('request') else None

        test = PHAdjustmentTest.objects.create(
            **validated_data,
            analyst=user if user and user.is_authenticated else None
        )

        for jar in jar_data:
            PHAdjustmentJarResult.objects.create(test=test, **jar)

        test.rank_results()
        return test

    def update(self, instance, validated_data):
        jar_data = validated_data.pop('jar_results', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if jar_data:
            instance.jar_results.all().delete()
            for jar in jar_data:
                PHAdjustmentJarResult.objects.create(test=instance, **jar)

            instance.rank_results()

        return instance


# ===========================================
# ✅ List Serializer (Optimized)
# ===========================================
class PHAdjustmentTestListSerializer(serializers.ModelSerializer):
    treatment_plant = serializers.StringRelatedField()
    analyst = serializers.StringRelatedField()
    optimal_jar = serializers.SerializerMethodField()

    class Meta:
        model = PHAdjustmentTest
        fields = ['id', 'treatment_plant', 'test_date', 'analyst',
                  'established_dosage_mg_per_l', 'optimal_jar']

    def get_optimal_jar(self, obj):
        optimal = obj.get_optimal_result()
        if not optimal:
            return None
        return {
            "jar_number": optimal.jar_number,
            "final_ph": optimal.final_ph,
            "dosage": optimal.dosage_mg_per_l
        }
