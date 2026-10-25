from rest_framework import viewsets, permissions, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import CustomUser, TreatmentPlant, AccountConfiguration
from .serializers import (
    TreatmentPlantSerializer, GroupSerializer, PermissionSerializer,
    CustomUserSerializer, AccountConfigurationSerializer
)
from .views import reauthenticate  # Import the reauthentication view


# =======================
# ✅ JWT-based Login View
# =======================
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response({'detail': 'Username and password are required'}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(request, username=username, password=password)
    if user is not None:
        if user.is_locked:
            return Response({'detail': 'Account is locked due to multiple failed login attempts'},
                            status=status.HTTP_403_FORBIDDEN)

        # reset failed attempts
        user.reset_failed_login_attempts()

        # generate tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }, status=status.HTTP_200_OK)

    return Response({'detail': 'Invalid username or password'}, status=status.HTTP_400_BAD_REQUEST)


# =======================
# 🔒 Secure Auth Endpoints
# =======================
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def check_username(request):
    username = request.data.get('username')
    if not username:
        return Response(
            {'detail': 'Username is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    exists = CustomUser.objects.filter(username=username).exists()
    return Response({'exists': exists}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def reset_password_request(request):
    username = request.data.get('username')
    try:
        user = CustomUser.objects.get(username=username)
        # generate reset token
        token = default_token_generator.make_token(user)
        # generate password reset URL
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        password_reset_url = f"http://localhost:3000/reset-password/{uid}/{token}/"

        context = {
            'user': user,
            'password_reset_url': password_reset_url
        }
        subject = 'Password Reset Requested'
        email_template_name = 'password_reset_email.html'
        email = render_to_string(email_template_name, context)

        send_mail(
            subject,
            email,
            'swanjala@nairobiwater.co.ke',
            [user.email],
            fail_silently=False,
        )
        return Response({'status': 'Password reset email sent'}, status=status.HTTP_200_OK)
    except CustomUser.DoesNotExist:
        return Response({'detail': 'User does not exist'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def reset_password_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)

        if default_token_generator.check_token(user, token):
            new_password = request.data.get('new_password')
            user.set_password(new_password)
            user.save()
            return Response({'status': 'Password has been reset'}, status=status.HTTP_200_OK)
        else:
            return Response({'detail': 'Invalid token or user ID'}, status=status.HTTP_400_BAD_REQUEST)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        return Response({'detail': 'Invalid request'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def set_cookie(request):
    token = request.data.get('token')
    if not token:
        return Response({"error": "Token is required"}, status=400)

    response = Response({"message": "Authentication cookie successfully set"})
    response.set_cookie(
        "auth_token",
        token,
        httponly=True,
        secure=False,  # Use True in production!
        samesite="Strict",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    return response


@api_view(['POST'])
def logout(request):
    if not request.auth:
        return Response({"message": "No active token found"}, status=status.HTTP_400_BAD_REQUEST)
    request.auth.delete()
    return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)


# =======================
# ViewSets
# =======================
class TreatmentPlantViewSet(viewsets.ModelViewSet):
    queryset = TreatmentPlant.objects.all()
    serializer_class = TreatmentPlantSerializer
    permission_classes = [permissions.IsAdminUser]

    @action(detail=False, methods=['post'], url_path='check-permissions')
    def check_access(self, request):
        if not request.user.has_perm('accounts.view_treatmentplant'):
            return Response({'detail': 'Permission denied. Please reauthenticate.'},
                            status=status.HTTP_403_FORBIDDEN)
        return Response({'detail': 'Permission granted.'}, status=status.HTTP_200_OK)


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAdminUser]


class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [permissions.IsAdminUser]


class CustomUserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = CustomUserSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'email']
    ordering_fields = ['username', 'email', 'assigned_treatment_plant__name']

    def get_permissions(self):
        if getattr(self, "action", None) == "me":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    def get_queryset(self):
        queryset = super().get_queryset()
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            return queryset.none()
        treatment_plant = self.request.query_params.get('treatment_plant')
        if treatment_plant:
            queryset = queryset.filter(assigned_treatment_plant__name=treatment_plant)
        return queryset

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def set_password(self, request, pk=None):
        user = self.get_object()
        password = request.data.get('password')
        user.set_password(password)
        user.save()
        return Response({'status': 'Password updated successfully'})


class AccountConfigurationViewSet(viewsets.ModelViewSet):
    queryset = AccountConfiguration.objects.all()
    serializer_class = AccountConfigurationSerializer
    permission_classes = [permissions.IsAdminUser]

    @action(detail=False, methods=['post'])
    def reauthenticate(self, request):
        """
        Re-authenticate the user when permissions are denied.
        Accepts username and password to generate new tokens.
        """
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({'detail': 'Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=username, password=password)

        if user is not None:
            if user.is_locked:
                return Response({'detail': 'Account is locked due to multiple failed login attempts'},
                                status=status.HTTP_403_FORBIDDEN)

            # Generate refresh token
            refresh = RefreshToken.for_user(user)
            return Response({
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
            }, status=status.HTTP_200_OK)

        return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)
