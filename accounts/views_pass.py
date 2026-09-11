import logging
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.password_validation import validate_password
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.utils.html import strip_tags
from django.dispatch import Signal
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser

logger = logging.getLogger(__name__)
password_reset_success = Signal()

# Utility: JWT tokens
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }

# Utility: Set tokens as cookies
def set_auth_cookies(response, tokens):
    response.set_cookie(
        key='access_token',
        value=tokens['access'],
        httponly=True,
        secure=True,
        samesite='Lax',
        max_age=getattr(settings, 'ACCESS_TOKEN_AGE', 3600)
    )
    response.set_cookie(
        key='refresh_token',
        value=tokens['refresh'],
        httponly=True,
        secure=True,
        samesite='Lax',
        max_age=getattr(settings, 'REFRESH_TOKEN_AGE', 7 * 24 * 3600)
    )

@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def password_reset_request(request):
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = CustomUser.objects.get(email=email)
    except CustomUser.DoesNotExist:
        return Response({"detail": "User with this email does not exist."}, status=status.HTTP_404_NOT_FOUND)

    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password/{uid}/{token}/"

    html_message = render_to_string("emails/password_reset.html", {
        "user": user,
        "reset_url": reset_url
    })

    try:
        send_mail(
            "Password Reset Request",
            strip_tags(html_message),
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False
        )
        logger.info(f"Password reset email sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send reset email to {user.email}: {str(e)}")
        return Response({"detail": "Error sending email."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"detail": "Password reset email sent."}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (CustomUser.DoesNotExist, ValueError, TypeError):
        return Response({"detail": "Invalid reset link."}, status=status.HTTP_400_BAD_REQUEST)

    if not default_token_generator.check_token(user, token):
        return Response({"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)

    new_password = request.data.get("password")
    if not new_password:
        return Response({"detail": "Password is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        validate_password(new_password, user)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save()

    password_reset_success.send(sender=CustomUser, user=user)

    tokens = get_tokens_for_user(user)
    response = Response({
        "detail": "Password has been reset successfully.",
        "tokens": tokens
    }, status=status.HTTP_200_OK)

    set_auth_cookies(response, tokens)
    logger.info(f"Password reset successful for user {user.email}")

    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')

    if not old_password or not new_password:
        return Response({"detail": "Both old_password and new_password are required."},
                        status=status.HTTP_400_BAD_REQUEST)

    # Verify old password is correct
    if not user.check_password(old_password):
        return Response({"detail": "Old password is incorrect."},
                        status=status.HTTP_400_BAD_REQUEST)

    # Validate new password strength
    try:
        validate_password(new_password, user)
    except Exception as e:
        # If multiple errors, join messages
        if hasattr(e, 'messages'):
            return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Set new password and save
    user.set_password(new_password)
    user.save()

    return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)
