from rest_framework import viewsets, filters, status
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from .models import AuditLogEntry, UserActivity
from .serializers import AuditLogEntrySerializer, UserActivitySerializer, AuditLogEntryWithUserActivitySerializer

class AuditLogEntryViewSet(viewsets.ModelViewSet):
    queryset = AuditLogEntry.objects.all().order_by('-timestamp')
    serializer_class = AuditLogEntrySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['user', 'result_status', 'priority', 'location']
    search_fields = ['user__username', 'action', 'ip_address', 'device', 'user_agent', 'location', 'description']
    ordering_fields = ['timestamp', 'priority']

    @action(detail=False, methods=['get'], url_path='by-user')
    def list_by_user(self, request):
        user = request.user
        queryset = self.get_queryset().filter(user=user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='details')
    def get_audit_details(self, request, pk=None):
        instance = self.get_object()
        serializer = AuditLogEntryWithUserActivitySerializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

class UserActivityViewSet(viewsets.ModelViewSet):
    queryset = UserActivity.objects.all().order_by('-timestamp')
    serializer_class = UserActivitySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['user', 'successful_attempt', 'location']
    search_fields = ['user__username', 'activity_type', 'ip_address', 'device', 'user_agent', 'location']
    ordering_fields = ['timestamp', 'duration']

    @action(detail=False, methods=['get'], url_path='by-user')
    def list_by_user(self, request):
        user = request.user
        queryset = self.get_queryset().filter(user=user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='details')
    def get_activity_details(self, request, pk=None):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)
