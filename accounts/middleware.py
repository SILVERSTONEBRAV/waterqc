from django.contrib.auth import get_user_model
from django.utils import timezone
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
import logging

# Custom User model
CustomUser = get_user_model()

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

class PasswordChangeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        user = request.user
        if not user.is_authenticated:
            return None

        logger.debug(f"User {user.username} authenticated status: {user.is_authenticated}")

        if not user.is_superuser and self.is_password_expired(user):
            logger.debug(f"Password expired for user: {user.username}")
            return redirect(reverse('password_change'))

        logger.debug(f"User {user.username} password status: valid")
        return None

    @staticmethod
    def is_password_expired(user):
        return timezone.now() > user.password_last_set + timezone.timedelta(days=28)
