from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model

from .models import Laboratory
from .serializers import LaboratorySerializer

User = get_user_model()

class LaboratoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Laboratory CRUD and custom actions.
    """
    queryset = Laboratory.objects.select_related('treatment_plant').all()
    serializer_class = LaboratorySerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['get'], url_path='users')
    def users(self, request, pk=None):
        lab = self.get_object()
        users = lab.get_lab_users()
        data = [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "groups": [group.name for group in user.groups.all()]
            }
            for user in users
        ]
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='roles')
    def roles(self, request, pk=None):
        lab = self.get_object()
        roles = lab.get_lab_user_roles()
        data = [
            {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email
                },
                "groupNames": group_names
            }
            for user, group_names in roles
        ]
        return Response(data, status=status.HTTP_200_OK)
