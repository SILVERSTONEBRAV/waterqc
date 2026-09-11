from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .models import (
    SamplingTime,
    WaterAnalysis,
    WaterAnalysisLog,
    TreatedWaterResult,
    ClarifiedWaterResult,
    CoagulatedWaterResult,
    RawWaterResult,
    NonConformity,
    NonConformityLog,
    Cause,
)
from t.models import (
    TreatedWaterLimit,
    ClarifiedWaterLimit,
    CoagulatedWaterLimit,
    RawWaterLimit,
    TreatmentPlant,
    TreatmentPlantPhase,
)
from accounts.models import CustomUser
from sc.models import Shift


# ---------------------------
# Basic Serializers
# ---------------------------

class SamplingTimeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SamplingTime
        fields = ['id', 'name', 'time']


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'first_name', 'last_name']


class TreatmentPlantSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreatmentPlant
        fields = ['id', 'name']


class TreatmentPlantPhaseSerializer(serializers.ModelSerializer):
    treatment_plant = TreatmentPlantSerializer(read_only=True)

    class Meta:
        model = TreatmentPlantPhase
        fields = ['id', 'name', 'treatment_plant']


class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = ['id', 'name', 'start_time', 'end_time']


# ---------------------------
# Logs
# ---------------------------

class WaterAnalysisLogSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(source='actor', read_only=True)
    new_state_display = serializers.CharField(source='get_new_state_display', read_only=True)

    class Meta:
        model = WaterAnalysisLog
        fields = ['id', 'new_state', 'new_state_display', 'user', 'remarks', 'sampled_at', 'created_at']


class NonConformityLogSerializer(serializers.ModelSerializer):
    actor = UserSummarySerializer(read_only=True)

    class Meta:
        model = NonConformityLog
        fields = ['id', 'action', 'remarks', 'actor', 'auto_generated', 'created_at']


# ---------------------------
# Cause Serializer
# ---------------------------

class CauseSerializer(serializers.ModelSerializer):
    created_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Cause
        fields = ['id', 'name', 'description', 'created_by']


# ---------------------------
# NonConformity Serializer
# ---------------------------

class NonConformitySerializer(serializers.ModelSerializer):
    analysis_id = serializers.PrimaryKeyRelatedField(
        queryset=WaterAnalysis.objects.all(),
        source='analysis',
        write_only=True
    )
    causes = CauseSerializer(many=True, read_only=True)
    causes_ids = serializers.PrimaryKeyRelatedField(
        queryset=Cause.objects.all(),
        many=True,
        write_only=True,
        source='causes'
    )
    triggered_by = UserSummarySerializer(read_only=True)
    logs = NonConformityLogSerializer(many=True, read_only=True)

    class Meta:
        model = NonConformity
        fields = [
            'id',
            'analysis_id',
            'parameter_name',
            'observed_value',
            'min_limit',
            'max_limit',
            'deviation',
            'status',
            'auto_detected',
            'corrective_action',
            'preventive_action',
            'causes',
            'causes_ids',
            'triggered_by',
            'resolved_at',
            'created_at',
            'updated_at',
            'logs',
        ]

    def validate(self, data):
        corrective_action = data.get('corrective_action', getattr(self.instance, 'corrective_action', None))
        preventive_action = data.get('preventive_action', getattr(self.instance, 'preventive_action', None))
        causes = data.get('causes', getattr(self.instance, 'causes', None))

        # Only allow full closure if causes + actions exist
        if data.get('status') == NonConformity.Status.CLOSED:
            if not corrective_action or not preventive_action or (not causes or len(causes) == 0):
                raise serializers.ValidationError(
                    _("NonConformity can only be fully closed if at least one cause exists "
                      "and both corrective & preventive actions are filled.")
                )
        return data


# ---------------------------
# WaterAnalysis Serializer
# ---------------------------

class WaterAnalysisSerializer(serializers.ModelSerializer):
    treatment_plant = TreatmentPlantSerializer(read_only=True)
    treatment_plant_id = serializers.PrimaryKeyRelatedField(
        queryset=TreatmentPlant.objects.all(),
        source='treatment_plant',
        write_only=True
    )

    treatment_plant_phase = TreatmentPlantPhaseSerializer(read_only=True)
    treatment_plant_phase_id = serializers.PrimaryKeyRelatedField(
        queryset=TreatmentPlantPhase.objects.all(),
        source='treatment_plant_phase',
        write_only=True
    )

    shift = ShiftSerializer(read_only=True)
    shift_id = serializers.PrimaryKeyRelatedField(
        queryset=Shift.objects.all(),
        source='shift',
        write_only=True,
        allow_null=True,
        required=False
    )

    analysis_time = SamplingTimeSerializer(read_only=True)
    analysis_time_id = serializers.PrimaryKeyRelatedField(
        queryset=SamplingTime.objects.all(),
        source='analysis_time',
        write_only=True
    )

    analysed_by = UserSummarySerializer(read_only=True)
    verified_by = UserSummarySerializer(read_only=True)
    approved_by = UserSummarySerializer(read_only=True)

    logs = WaterAnalysisLogSerializer(many=True, read_only=True)
    nonconformities = NonConformitySerializer(many=True, read_only=True)
    state_display = serializers.CharField(source='get_state_display', read_only=True)

    class Meta:
        model = WaterAnalysis
        fields = [
            'id',
            'reference_id',
            'treatment_plant',
            'treatment_plant_id',
            'treatment_plant_phase',
            'treatment_plant_phase_id',
            'shift',
            'shift_id',
            'analysis_time',
            'analysis_time_id',
            'state',
            'state_display',
            'notes',
            'analysed_at',
            'verified_at',
            'approved_at',
            'analysed_by',
            'verified_by',
            'approved_by',
            'created_at',
            'updated_at',
            'logs',
            'nonconformities',
        ]

    def validate(self, data):
        treatment_plant = data.get('treatment_plant', getattr(self.instance, 'treatment_plant', None))
        treatment_plant_phase = data.get('treatment_plant_phase', getattr(self.instance, 'treatment_plant_phase', None))
        shift = data.get('shift', getattr(self.instance, 'shift', None))
        analysis_time = data.get('analysis_time', getattr(self.instance, 'analysis_time', None))

        errors = {}

        if treatment_plant_phase and treatment_plant and treatment_plant_phase.treatment_plant_id != treatment_plant.id:
            errors['treatment_plant_phase'] = _("Phase does not belong to the selected treatment plant.")

        qs = WaterAnalysis.objects.filter(
            treatment_plant=treatment_plant,
            analysis_time=analysis_time,
            shift=shift
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            errors['analysis_time'] = _("Analysis for this plant, time, and shift already exists.")

        if errors:
            raise serializers.ValidationError(errors)

        return data


# ---------------------------
# Base Result Serializer
# ---------------------------
class BaseResultSerializer(serializers.ModelSerializer):
    analysis_created_at = serializers.DateTimeField(
        source="analysis.created_at",
        read_only=True
    )
    analysis_updated_at = serializers.DateTimeField(
        source="analysis.updated_at",
        read_only=True
    )

    source = serializers.ChoiceField(
        choices=[("sensor", "Sensor"), ("manual", "Manual Entry")],
        default="manual"
    )

    class Meta:
        abstract = True
        fields = [
            "id",
            "analysis",
            "value",
            "source",
            "analysis_created_at",
            "analysis_updated_at",
        ]

    # ---------------------------
    # VALIDATION
    # ---------------------------

    def validate_value(self, value):
        if value is None:
            raise serializers.ValidationError("Every parameter must have a value.")
        if value < 0:
            raise serializers.ValidationError("Negative values are not allowed.")
        return value

    def validate(self, attrs):
        """
        Ensures:
        - Manual entry allowed if no sensor
        - Sensor values must still have a value
        """
        source = attrs.get("source", "manual")
        value = attrs.get("value")

        if source == "sensor" and value is None:
            raise serializers.ValidationError({
                "value": "Sensor-linked results must include a value."
            })

        return attrs




# ---------------------------
# Water Result Serializers
# ---------------------------

class TreatedWaterResultSerializer(BaseResultSerializer):
    parameter = serializers.StringRelatedField(read_only=True)

    parameter_id = serializers.PrimaryKeyRelatedField(
        queryset=TreatedWaterLimit.objects.all(),
        source="parameter",
        write_only=True,
        required=True
    )

    class Meta(BaseResultSerializer.Meta):
        model = TreatedWaterResult
        fields = BaseResultSerializer.Meta.fields + [
            "parameter",
            "parameter_id",
        ]


class ClarifiedWaterResultSerializer(BaseResultSerializer):
    parameter = serializers.StringRelatedField(read_only=True)

    parameter_id = serializers.PrimaryKeyRelatedField(
        queryset=ClarifiedWaterLimit.objects.all(),
        source="parameter",
        write_only=True,
        required=True
    )

    class Meta(BaseResultSerializer.Meta):
        model = ClarifiedWaterResult
        fields = BaseResultSerializer.Meta.fields + [
            "parameter",
            "parameter_id",
        ]


class CoagulatedWaterResultSerializer(BaseResultSerializer):
    parameter = serializers.StringRelatedField(read_only=True)

    parameter_id = serializers.PrimaryKeyRelatedField(
        queryset=CoagulatedWaterLimit.objects.all(),
        source="parameter",
        write_only=True,
        required=True
    )

    class Meta(BaseResultSerializer.Meta):
        model = CoagulatedWaterResult
        fields = BaseResultSerializer.Meta.fields + [
            "parameter",
            "parameter_id",
        ]


class RawWaterResultSerializer(BaseResultSerializer):
    parameter = serializers.StringRelatedField(read_only=True)

    parameter_id = serializers.PrimaryKeyRelatedField(
        queryset=RawWaterLimit.objects.all(),
        source="parameter",
        write_only=True,
        required=True
    )

    class Meta(BaseResultSerializer.Meta):
        model = RawWaterResult
        fields = BaseResultSerializer.Meta.fields + [
            "parameter",
            "parameter_id",
        ]
