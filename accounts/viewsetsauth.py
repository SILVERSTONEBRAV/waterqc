from django.http import HttpRequest
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.contrib.auth import authenticate
from django.conf import settings
from .models import CustomUser
from .serializers import CustomUserSerializer
from django.utils.timezone import now
from datetime import timedelta

User = CustomUser


def get_cookie_settings():
    return {
        "path": "/",
        "domain": getattr(settings, "SESSION_COOKIE_DOMAIN", None),
        "samesite": "Strict",
        "secure": True,
        "httponly": True,
    }


# Login View - Authenticates user and issues JWT tokens
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: HttpRequest, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({"detail": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token

        access_expiration = now() + settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME']
        refresh_expiration = now() + settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']

        return Response({
            "access": str(access_token),
            "refresh": str(refresh),
            "access_expires": access_expiration.isoformat(),
            "refresh_expires": refresh_expiration.isoformat(),
            "user": CustomUserSerializer(user).data
        })

class LogoutView(APIView):
    def post(self, request):
        refresh_token = request.data.get("refresh_token")

        try:
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except TokenError:
            pass  # Ignore if already blacklisted or invalid

        response = Response({"detail": "Logout successful."}, status=status.HTTP_205_RESET_CONTENT)

        # ✅ Correct usage: don't pass secure, httponly, etc.
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")

        return response


# Set Cookie View - Stores tokens in HttpOnly cookies
class SetCookieView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: HttpRequest, *args, **kwargs):
        access_token = request.data.get('access_token')
        refresh_token = request.data.get('refresh_token')

        if not access_token or not refresh_token:
            return Response({"detail": "Access and refresh tokens are required."}, status=status.HTTP_400_BAD_REQUEST)

        response = Response({'detail': 'Tokens set successfully.'}, status=status.HTTP_200_OK)

        cookie_settings = get_cookie_settings()
        response.set_cookie('access_token', access_token, **cookie_settings)
        response.set_cookie('refresh_token', refresh_token, **cookie_settings)

        return response


@api_view(['GET', 'POST'])  # Accepts both GET and POST
@permission_classes([permissions.AllowAny])
def check_username(request: HttpRequest):
    if request.method == 'GET':
        username = request.query_params.get('username')  # GET: from query string
    else:
        username = request.data.get('username')  # POST: from request body

    if not username:
        return Response({'detail': 'Username is required.'}, status=status.HTTP_400_BAD_REQUEST)

    exists = CustomUser.objects.filter(username=username).exists()
    return Response({'exists': exists}, status=status.HTTP_200_OK)



# Get current authenticated user info
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: HttpRequest):
        serializer = CustomUserSerializer(request.user)
        return Response(serializer.data)
