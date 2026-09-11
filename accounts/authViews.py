#accounts/authViews.py
import logging
import uuid
from django.conf import settings
from django.utils import timezone
from django.urls import reverse_lazy
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth import (authenticate, login as auth_login,logout as auth_logout, get_user_model, update_session_auth_hash,)
from core.models import SystemConfiguration
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.shortcuts import resolve_url
from django.views import View
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from CompanyInfo.context_processors import company_context
from .models import CustomUser
from core.models import validate_pf_number, validate_mobile_number, validate_password_strength
from django.urls import reverse, reverse_lazy, NoReverseMatch
from django.contrib import messages
import logging


logger = logging.getLogger(__name__)
User = get_user_model()

def get_company_context(request=None):
    return company_context(request)

def get_config():
    from core.models import SystemConfiguration
    return SystemConfiguration.objects.get_or_create(pk=1)[0]


# =========================================================
# HELPERS
# =========================================================
def get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


# =========================================================
# CHECK USERNAME
# =========================================================


class CheckUsernameView(View):
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        username = request.POST.get("username", "").strip().upper()
        exists = CustomUser.objects.filter(username=username).exists()
        return JsonResponse({"exists": exists})



# =========================================================
# RESET PASSWORD REQUEST
# =========================================================
class ResetPasswordRequestView(View):
    def post(self, request):
        username = request.POST.get("username", "").strip().upper()

        user = CustomUser.objects.filter(username=username).first()
        if not user:
            return JsonResponse({"success": False, "message": "User not found."})

        token = uuid.uuid4().hex
        request.session[f"reset_{user.pk}"] = token

        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}&uid={user.pk}"

        try:
            send_mail(
                subject="Password Reset Request",
                message=f"Use this link to reset your password:\n{reset_link}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

            logger.info(f"Password reset requested for {user.username}")

            return JsonResponse({"success": True, "message": "Reset email sent."})

        except Exception as e:
            logger.error(f"Reset email failed for {user.username}: {e}")
            return JsonResponse({"success": False, "message": "Failed to send email."})


# =========================================================
# CHANGE PASSWORD
# =========================================================
# =========================================================
# CHANGE PASSWORD
# =========================================================
class ChangePasswordView(LoginRequiredMixin, View):
    template_name = "accounts/profile/change_password.html"
    def get(self, request):
        context = get_company_context(request)
        context["password_changed"] = False
        return render(request, self.template_name, context)
    def post(self, request):
        user = request.user
        old_password = request.POST.get("old_password", "").strip()
        new_password = request.POST.get("new_password", "").strip()
        confirm_password = request.POST.get("confirm_password", "").strip()

        context = get_company_context(request)
        context["password_changed"] = False
        if not user.check_password(old_password):
            context["error"] = "Current password is incorrect."
            return render(request, self.template_name, context)
        if new_password != confirm_password:
            context["error"] = "Passwords do not match."
            return render(request, self.template_name, context)
        if user.check_password(new_password):
            context["error"] = (
                "New password cannot be the same as the current password."
            )
            return render(request, self.template_name, context)

        try:
            validate_password_strength(new_password)
        except ValidationError as e:
            context["error"] = e.messages[0]
            return render(request, self.template_name, context)
        user.set_password(new_password)
        user.password_last_set = timezone.now()
        user.save(update_fields=[
            "password",
            "password_last_set",
        ])
        update_session_auth_hash(request, user)

        logger.info(
            "Password changed by %s from IP %s",
            user.username,
            get_client_ip(request),
        )
        context["success"] = "Password changed successfully."
        context["password_changed"] = True
        return render(request, self.template_name, context)