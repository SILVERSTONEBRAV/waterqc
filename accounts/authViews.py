#accounts/authViews.py
import logging

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
# RESET PASSWORD REQUEST  (10-minute expiring signed token)
# =========================================================
class ResetPasswordRequestView(View):
    """
    Accepts AJAX POST with ``username``.
    Looks up the user, generates a signed token (10-min TTL),
    builds a reset URL, and dispatches an HTML email.
    """

    RESET_TOKEN_MAX_AGE = 600  # 10 minutes in seconds

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        username = request.POST.get("username", "").strip().upper()

        if not username:
            return JsonResponse({"success": False, "message": "Username is required."})

        user = CustomUser.objects.filter(username=username).first()
        if not user:
            # Intentionally vague to prevent user enumeration
            return JsonResponse({"success": True, "message": "If the account exists, a reset email has been sent."})

        if not user.email:
            return JsonResponse({"success": False, "message": "No email address associated with this account. Contact your administrator."})

        # ── Build signed token with timestamp ──
        from django.core.signing import TimestampSigner
        signer = TimestampSigner()
        token = signer.sign(str(user.pk))

        reset_path = reverse("accounts:password_reset_confirm", kwargs={"token": token})
        reset_url = request.build_absolute_uri(reset_path)

        # ── Render email ──
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags

        context = {
            "user": user,
            "reset_url": reset_url,
            "expiry_minutes": self.RESET_TOKEN_MAX_AGE // 60,
        }
        html_message = render_to_string("accounts/emails/password_reset_email.html", context)
        plain_message = strip_tags(html_message)

        try:
            send_mail(
                subject="Password Reset Request",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
            logger.info("Password reset email sent for user=%s to=%s", user.username, user.email)
        except Exception as e:
            logger.error("Password reset email failed for user=%s: %s", user.username, e)
            return JsonResponse({"success": False, "message": "Failed to send email. Please try again later."})

        # Mask actual email for privacy
        email = user.email
        at_idx = email.index("@")
        masked = email[0] + "***" + email[at_idx - 1:] if at_idx > 1 else email
        return JsonResponse({"success": True, "message": f"Password reset email sent to {masked}."})


# =========================================================
# PASSWORD RESET CONFIRM  (token-validated form)
# =========================================================
class PasswordResetConfirmView(View):
    """
    GET  – Validates the signed token (10-min TTL), renders the new-password form.
    POST – Validates token again, applies the new password.
    """

    template_name = "accounts/password_reset_confirm.html"
    RESET_TOKEN_MAX_AGE = 600  # 10 minutes

    def _unsign_token(self, token):
        """Return (user_pk, error_message) tuple."""
        from django.core.signing import TimestampSigner, SignatureExpired, BadSignature
        signer = TimestampSigner()
        try:
            user_pk = signer.unsign(token, max_age=self.RESET_TOKEN_MAX_AGE)
            return user_pk, None
        except SignatureExpired:
            return None, "This password reset link has expired (10-minute limit). Please request a new one."
        except BadSignature:
            return None, "Invalid password reset link. Please request a new one."

    def get(self, request, token):
        user_pk, error = self._unsign_token(token)
        ctx = get_company_context(request)
        if error:
            ctx["error"] = error
            ctx["token_valid"] = False
        else:
            ctx["token_valid"] = True
            ctx["token"] = token
        return render(request, self.template_name, ctx)

    def post(self, request, token):
        user_pk, error = self._unsign_token(token)
        ctx = get_company_context(request)

        if error:
            ctx["error"] = error
            ctx["token_valid"] = False
            return render(request, self.template_name, ctx)

        user = CustomUser.objects.filter(pk=user_pk).first()
        if not user:
            ctx["error"] = "User account not found."
            ctx["token_valid"] = False
            return render(request, self.template_name, ctx)

        new_password = request.POST.get("new_password", "").strip()
        confirm_password = request.POST.get("confirm_password", "").strip()

        if not new_password or not confirm_password:
            ctx["error"] = "Both password fields are required."
            ctx["token_valid"] = True
            ctx["token"] = token
            return render(request, self.template_name, ctx)

        if new_password != confirm_password:
            ctx["error"] = "Passwords do not match."
            ctx["token_valid"] = True
            ctx["token"] = token
            return render(request, self.template_name, ctx)

        try:
            validate_password_strength(new_password)
        except ValidationError as e:
            ctx["error"] = e.messages[0] if hasattr(e, 'messages') else str(e)
            ctx["token_valid"] = True
            ctx["token"] = token
            return render(request, self.template_name, ctx)

        user.set_password(new_password)
        user.password_last_set = timezone.now()
        user.save(update_fields=["password", "password_last_set"])

        logger.info("Password reset completed for user=%s from IP=%s", user.username, get_client_ip(request))

        ctx["success"] = True
        ctx["token_valid"] = False  # Prevent re-submission
        return render(request, self.template_name, ctx)


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


class SessionCheckView(View):
    """
    Report whether the current request still has an authenticated session.
    """

    def get(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return JsonResponse({"active": False, "reason": "unauthenticated"}, status=401)

        return JsonResponse({"active": True, "username": user.username})