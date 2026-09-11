from django.http import HttpRequest
from django.utils.timezone import now
from django.conf import settings
from django.contrib.auth import authenticate

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status

from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken

from .models import CustomUser
from .serializers import CustomUserSerializer

User = CustomUser

# ========================
# 🔐 Cookie Settings
# ========================
def get_cookie_settings():
    settings_dict = {
        "path": "/",
        "httponly": True,
        "secure": not settings.DEBUG,
        "samesite": "Lax",
    }
    if not settings.DEBUG:
        settings_dict["domain"] = getattr(settings, "SESSION_COOKIE_DOMAIN", None)
    return settings_dict


# ========================
# 🔓 Login
# ========================
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: HttpRequest, *args, **kwargs):
        username = request.data.get("username")
        password = request.data.get("password")

        if not username or not password:
            return Response(
                {"detail": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)
        if not user:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token

        access_expiration = now() + settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
        refresh_expiration = now() + settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]

        return Response({
            "access": str(access_token),
            "refresh": str(refresh),
            "access_expires": access_expiration.isoformat(),
            "refresh_expires": refresh_expiration.isoformat(),
            "user": CustomUserSerializer(user).data,
        })


# ========================
# 🚪 Logout
# ========================
class LogoutView(APIView):
    def post(self, request: HttpRequest):
        refresh_token = request.data.get("refresh_token")

        try:
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except TokenError:
            pass

        response = Response(
            {"detail": "Logout successful."},
            status=status.HTTP_205_RESET_CONTENT,
        )
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")
        return response


# ========================
# 🍪 Set Cookies
# ========================
@authentication_classes([])  # ✅ Disable auth to avoid 401 during set-cookie
@permission_classes([AllowAny])
class SetCookieView(APIView):
    def post(self, request: HttpRequest, *args, **kwargs):
        access_token = request.data.get("access_token")
        refresh_token = request.data.get("refresh_token")

        if not access_token or not refresh_token:
            return Response(
                {"detail": "Access and refresh tokens are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = Response(
            {"detail": "Tokens set successfully."},
            status=status.HTTP_200_OK,
        )

        cookie_settings = get_cookie_settings()
        response.set_cookie("access_token", access_token, **cookie_settings)
        response.set_cookie("refresh_token", refresh_token, **cookie_settings)

        return response


# ========================
# ❌ Clear Cookies
# ========================
class ClearCookieView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: HttpRequest):
        response = Response({"detail": "Cookies cleared."}, status=status.HTTP_200_OK)
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")
        return response


# ========================
# 🔁 Refresh Token via Cookie
# ========================
class CookieTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request: HttpRequest, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"detail": "Refresh token not found in cookies."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TokenRefreshSerializer(data={"refresh": refresh_token})

        try:
            serializer.is_valid(raise_exception=True)
        except InvalidToken:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(serializer.validated_data, status=status.HTTP_200_OK)


# ========================
# 🔎 Check Username Exists (Public)
# ========================
@api_view(["GET", "POST"])
@authentication_classes([])  # ✅ Public access
@permission_classes([AllowAny])
def check_username(request: HttpRequest):
    if request.method == "GET":
        username = request.query_params.get("username")
    else:
        username = request.data.get("username")

    if not username:
        return Response(
            {"detail": "Username is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    exists = CustomUser.objects.filter(username=username).exists()
    return Response({"exists": exists}, status=status.HTTP_200_OK)


# ========================
# 👤 Get Current User
# ========================
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: HttpRequest):
        serializer = CustomUserSerializer(request.user)
        return Response(serializer.data)
