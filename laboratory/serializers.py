from rest_framework import serializers
from .models import Laboratory
from t.models import TreatmentPlant  # Adjust if your app is not named `t`

class TreatmentPlantSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreatmentPlant
        fields = ['id', 'name']

class LaboratorySerializer(serializers.ModelSerializer):
    treatment_plant = TreatmentPlantSerializer(read_only=True)
    treatment_plant_id = serializers.PrimaryKeyRelatedField(
        queryset=TreatmentPlant.objects.all(),
        source='treatment_plant',
        write_only=True
    )

    class Meta:
        model = Laboratory
        fields = ['id', 'name', 'treatment_plant', 'treatment_plant_id', 'created_at']
        read_only_fields = ['id', 'created_at']
