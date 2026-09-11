import logging
import asyncio
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework import status
from .models import CustomUser
from .serializers import CustomUserSerializer
from asgiref.sync import sync_to_async

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class RegisterAPIView(APIView):
    async def post(self, request):
        serializer = CustomUserSerializer(data=request.data)
        if serializer.is_valid():
            user = await sync_to_async(serializer.save)()
            token, created = await sync_to_async(Token.objects.get_or_create)(user=user)
            logger.info(f"New user registered via API: {user.username}")
            return Response({'token': token.key}, status=status.HTTP_201_CREATED)
        logger.error(f"Registration failed via API: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginAPIView(APIView):
    async def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = await sync_to_async(authenticate)(username=username, password=password)
        if user:
            await sync_to_async(login)(request, user)
            token, created = await sync_to_async(Token.objects.get_or_create)(user=user)
            logger.info(f"User logged in via API: {user.username}")
            return Response({'token': token.key}, status=status.HTTP_200_OK)
        logger.error("Login failed via API: Incorrect credentials")
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)

class ProfileAPIView(APIView):
    async def get(self, request):
        user = request.user
        serializer = CustomUserSerializer(user)
        logger.info(f"Fetched profile via API: {user.username}")
        return Response(serializer.data, status=status.HTTP_200_OK)

    async def put(self, request):
        user = request.user
        serializer = CustomUserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            await sync_to_async(serializer.save)()
            logger.info(f"Updated profile via API: {user.username}")
            return Response(serializer.data)
        logger.error(f"Profile update failed via API: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutAPIView(APIView):
    async def post(self, request):
        await sync_to_async(logout)(request)
        logger.info("User logged out via API")
        return Response({'message': 'Logged out successfully'}, status=status.HTTP_200_OK)
