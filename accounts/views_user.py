from typing import List
import logging

from django.contrib.auth import authenticate
from django.contrib.auth.models import Group, Permission
from asgiref.sync import sync_to_async

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action, parser_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from .models import CustomUser, AccountConfiguration, Section
from t.models import TreatmentPlant
from .serializers import (
    CustomUserSerializer,
    AccountConfigurationSerializer,
    TreatmentPlantSerializer,
    GroupSerializer,
    PermissionSerializer,
    SectionSerializer,
)
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)


# -------------------------------
# CUSTOM USER VIEWSET
# -------------------------------
class CustomUserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = CustomUserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'groups', 'assigned_treatment_plant', 'section']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['date_joined', 'last_login', 'username', 'email']
    ordering = ['username']

    def get_queryset(self):
        qs = super().get_queryset()
        treatment_plant = self.request.query_params.get('treatment_plant')
        section = self.request.query_params.get('section')
        if treatment_plant:
            qs = qs.filter(assigned_treatment_plant__name=treatment_plant)
        if section:
            qs = qs.filter(section__code=section)
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    # -------------------------------
    # Async create/update hooks
    # -------------------------------
    async def perform_create(self, serializer):
        await sync_to_async(serializer.save)()

    async def perform_update(self, serializer):
        await sync_to_async(serializer.save)()

    # -------------------------------
    # Current user info
    # -------------------------------
    @action(detail=False, methods=['get'])
    async def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    # -------------------------------
    # Password update
    # -------------------------------
    @action(detail=True, methods=['post'])
    async def set_password(self, request, pk=None):
        user = await sync_to_async(self.get_object)()
        new_password = request.data.get('password')
        if not new_password:
            return Response({'detail': 'Password is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from django.contrib.auth.password_validation import validate_password
            validate_password(new_password, user)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        await sync_to_async(user.save)()
        return Response({'detail': 'Password updated successfully.'})

    # -------------------------------
    # Profile picture upload
    # -------------------------------
    @action(detail=True, methods=['post'])
    @parser_classes([MultiPartParser])
    async def upload_picture(self, request, pk=None):
        user = await sync_to_async(self.get_object)()
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        user.profile_picture = file
        await sync_to_async(user.save)()
        return Response({
            'detail': 'Profile picture uploaded successfully',
            'profile_picture_url': request.build_absolute_uri(user.profile_picture.url),
            'user_id': user.id,
        })

    # -------------------------------
    # Admin autofill endpoint
    # -------------------------------
    @action(detail=True, methods=['get'])
    async def profile_info(self, request, pk=None):
        user = await sync_to_async(self.get_object)()
        full_name = user.get_full_name() or user.username
        return Response({
            "full_name": full_name,
            "email": user.email,
            "phone": user.mobile_number or ""
        })


# -------------------------------
# SECTION VIEWSET
# -------------------------------
class SectionViewSet(viewsets.ModelViewSet):
    queryset = Section.objects.all()
    serializer_class = SectionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['code', 'name']
    ordering_fields = ['name', 'code']
    ordering = ['code']


# -------------------------------
# TREATMENT PLANT VIEWSET
# -------------------------------
class TreatmentPlantViewSet(viewsets.ModelViewSet):
    queryset = TreatmentPlant.objects.all()
    serializer_class = TreatmentPlantSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    async def check_permissions(self, request):
        perms = ['accounts.view_treatmentplant']
        granted = {p: request.user.has_perm(p) for p in perms}
        return Response({"permissions": granted})


# -------------------------------
# GROUP VIEWSET
# -------------------------------
class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated]


# -------------------------------
# PERMISSION VIEWSET
# -------------------------------
class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]


# -------------------------------
# ACCOUNT CONFIGURATION VIEWSET
# -------------------------------
class AccountConfigurationViewSet(viewsets.ModelViewSet):
    queryset = AccountConfiguration.objects.all()
    serializer_class = AccountConfigurationSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    @action(detail=False, methods=['post'])
    async def reauthenticate(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        if not username or not password:
            return Response({'detail': 'Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = await sync_to_async(authenticate)(username=username, password=password)
        if user is not None:
            if getattr(user, "is_locked", False):
                return Response({'detail': 'Account is locked due to multiple failed login attempts'},
                                status=status.HTTP_403_FORBIDDEN)
            refresh = RefreshToken.for_user(user)
            return Response({
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
            })
        return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)
