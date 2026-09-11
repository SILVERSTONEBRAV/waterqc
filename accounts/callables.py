import logging
import asyncio
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from .models import CustomUser
from rest_framework.authtoken.models import Token
from asgiref.sync import sync_to_async

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Authenticate user asynchronously
async def async_authenticate(username, password):
    user = await sync_to_async(authenticate)(username=username, password=password)
    if user is None:
        logger.error("Authentication failed: Invalid credentials")
        raise ValidationError("Invalid credentials")
    return user

# Login user asynchronously
async def async_login(request, user):
    await sync_to_async(login)(request, user)
    logger.info(f"User logged in: {user.username}")

# Logout user asynchronously
async def async_logout(request):
    await sync_to_async(logout)(request)
    logger.info("User logged out successfully")

# Generate token asynchronously
async def async_generate_token(user):
    token, created = await sync_to_async(Token.objects.get_or_create)(user=user)
    logger.info(f"Token generated for user: {user.username}")
    return token

# Save new user and hash password
async def async_save_user(serializer):
    user = await sync_to_async(serializer.save)()
    logger.info(f"New user saved: {user.username}")
    return user

# Update user profile asynchronously
async def async_update_user(serializer, partial=False):
    if serializer.is_valid():
        user = await sync_to_async(serializer.save)(partial=partial)
        logger.info(f"User profile updated: {user.username}")
        return user
    else:
        logger.error(f"Profile update failed: {serializer.errors}")
        raise ValidationError(serializer.errors)
