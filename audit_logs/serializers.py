from rest_framework import serializers
from .models import AuditLogEntry, UserActivity

class UserActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivity
        fields = '__all__'

class AuditLogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLogEntry
        fields = '__all__'

class AuditLogEntryWithUserActivitySerializer(serializers.ModelSerializer):
    user_activities = UserActivitySerializer(many=True, read_only=True)

    class Meta:
        model = AuditLogEntry
        fields = '__all__'
