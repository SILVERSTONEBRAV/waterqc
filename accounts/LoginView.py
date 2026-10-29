import logging
from typing import Optional
from django.shortcuts import resolve_url, render, redirect
from django.urls import NoReverseMatch
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, get_user_model
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.utils import timezone
from django.middleware.csrf import get_token
from django.views import View
from django.http import JsonResponse
from .utils import get_user_landing_url

from core.models import SystemConfiguration

logger = logging.getLogger(__name__)
User = get_user_model()


class LoginView(View):
    template_name = "accounts/login.html"

    max_failed_attempts = getattr(settings, "MAX_FAILED_LOGIN_ATTEMPTS", 5)

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self.config = self._get_config_safe()
        self.group_map = self._load_group_map()
        self.last_module_key = getattr(settings, "LOGIN_SESSION_LAST_MODULE_KEY", "last_module")
        self.last_url_key = getattr(settings, "LOGIN_SESSION_LAST_URL_KEY", "last_url")
        self.last_page_key = getattr(settings, "LOGIN_SESSION_LAST_PAGE_KEY", "last_visited_url")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        get_token(request)  # 🔥 FORCE CSRF COOKIE

        if request.user.is_authenticated:
            return redirect(self._resolve_landing(request, request.user))

        reason = request.GET.get("reason", "")
        error_msg = ""
        if reason == "logged_out":
            error_msg = "You have been logged out."

        response = render(request, self.template_name, {
            "username": "",
            "error": error_msg,
            "next": request.GET.get("next", ""),
            "session_expired": False,
            "remember_me": False,
        })
        return self._disable_login_caching(response)

    def post(self, request):
        is_ajax = self._is_ajax(request)

        # -----------------------------
        # FORCE CONSISTENT INPUT PARSING
        # -----------------------------
        try:
            username = (request.POST.get("username") or "").strip().upper()
            password = request.POST.get("password") or ""
        except Exception:
            username = ""
            password = ""

        # -----------------------------
        # DEBUG SAFETY (prevents your HTMLDivElement bug confusion)
        # -----------------------------
        if not isinstance(username, str):
            username = str(username)
        if not isinstance(password, str):
            password = str(password)

        # -----------------------------
        # VALIDATION
        # -----------------------------
        if not username or not password:
            return self._fail(
                request,
                username,
                "Username and password required",
                is_ajax
            )

        # -----------------------------
        # AUTHENTICATION
        # -----------------------------
        user = authenticate(request, username=username, password=password)

        if user is None:
            return self._handle_failed_login(request, username, is_ajax)

        # -----------------------------
        # ACCOUNT VALIDATION
        # -----------------------------
        validation_error = self._validate_user(user)
        if validation_error:
            return self._fail(request, username, validation_error, is_ajax)

        # -----------------------------
        # LOGIN
        # -----------------------------
        auth_login(request, user)
        self._initialize_session(request, user, remember=False)

        request.session.save()

        redirect_url = self._resolve_landing(request, user)

        logger.info(
            "LOGIN_SUCCESS user=%s ip=%s groups=%s",
            username,
            self._ip(request),
            self._groups(user)
        )

        # -----------------------------
        # ALWAYS JSON FOR AJAX
        # -----------------------------
        if is_ajax:
            response = JsonResponse({
                "success": True,
                "redirect": redirect_url
            })
            return self._disable_login_caching(response)

        return self._disable_login_caching(redirect(redirect_url))
    def _initialize_session(self, request, user, remember: bool = False):
        # auth_login has already rotated the session key. Keep this session
        # independent so signing in elsewhere does not invalidate it.
        request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        request.session.update({
            "user_id": user.pk,
            "username": user.username,
            "login_ts": timezone.now().timestamp(),
            "primary_group": self._primary_group(user),
        })
        user.failed_login_attempts = 0
        user.is_locked = False
        user.last_login = timezone.now()
        user.save(update_fields=["failed_login_attempts", "is_locked", "last_login"])


    def _handle_failed_login(self, request, username, is_ajax):
        error = "Invalid credentials"

        try:
            user = User.objects.get(username=username)

            user.increment_failed_login_attempts()

            if user.failed_login_attempts >= self.max_failed_attempts:
                user.is_locked = True
                user.save(update_fields=["is_locked"])
                error = "Account locked due to repeated attempts"

        except User.DoesNotExist:
            pass

        logger.warning("LOGIN_FAILED user=%s ip=%s", username, self._ip(request))

        return self._fail(request, username, error, is_ajax)

    def _validate_user(self, user):
        if user is None:
            return "Authentication failed"

        try:
            if getattr(user, "is_locked", False):
                logger.warning(
                    "VALIDATION_LOCKED user=%s",
                    user.username,
                )
                return "Account locked"

            if not user.is_active:
                logger.warning(
                    "VALIDATION_INACTIVE user=%s",
                    user.username,
                )
                return "Account inactive"

            if hasattr(user, "is_password_expired"):
                try:
                    if user.is_password_expired():
                        logger.warning(
                            "VALIDATION_PASSWORD_EXPIRED user=%s",
                            user.username,
                        )
                        return "Password expired"
                except Exception as exc:
                    logger.exception(
                        "PASSWORD_EXPIRY_CHECK_ERROR user=%s error=%s",
                        user.username,
                        exc,
                    )

            if user.is_superuser:
                logger.info(
                    "VALIDATION_SUPERUSER user=%s",
                    user.username,
                )
                return None

            groups = self._groups(user)

            if not groups:
                logger.warning(
                    "VALIDATION_NO_GROUPS user=%s",
                    user.username,
                )
                return "No group assigned"

            matched_groups = [
                g for g in groups
                if g in self.group_map
            ]

            if not matched_groups:
                logger.warning(
                    "VALIDATION_NO_MAPPING user=%s groups=%s",
                    user.username,
                    groups,
                )
                return "No dashboard mapping found"

            logger.info(
                "VALIDATION_SUCCESS user=%s groups=%s",
                user.username,
                matched_groups,
            )

            return None

        except Exception as exc:
            logger.exception(
                "VALIDATION_ERROR user=%s error=%s",
                getattr(user, "username", "unknown"),
                exc,
            )
            return "Unable to validate account"

    from accounts.utils import get_user_landing_url

    def _resolve_landing(self, request, user):
        return get_user_landing_url(user)
    def _resolve_target(self, target: str):
        if target is None:
            raise ImproperlyConfigured(
                "Redirect target is None"
            )

        target = str(target).strip()

        if not target:
            raise ImproperlyConfigured(
                "Redirect target is empty"
            )

        try:
            if target.startswith("/"):
                return target

            resolved = resolve_url(target)

            logger.debug(
                "TARGET_RESOLVED name=%s resolved=%s",
                target,
                resolved,
            )

            return resolved

        except NoReverseMatch as exc:
            logger.error(
                "TARGET_RESOLUTION_FAILED target=%s",
                target,
            )

            raise ImproperlyConfigured(
                f"Invalid redirect target: {target}"
            ) from exc

    def _safe_next(self, url: Optional[str]):
        if not url:
            return None

        try:
            url = str(url).strip()

            if not url:
                return None

            if not url.startswith("/"):
                return None

            lowered = url.lower()

            blocked_tokens = (
                "//",
                "\\",
                "javascript:",
                "vbscript:",
                "data:",
                "http://",
                "https://",
            )

            if any(
                    token in lowered
                    for token in blocked_tokens
            ):
                logger.warning(
                    "UNSAFE_NEXT_REJECTED url=%s",
                    url,
                )
                return None

            return url

        except Exception:
            return None

    def _groups(self, user):
        try:
            groups = [
                str(name).strip().upper()
                for name in user.groups.values_list(
                    "name",
                    flat=True,
                )
            ]

            return sorted(
                list(set(groups))
            )

        except Exception as exc:
            logger.exception(
                "GROUP_FETCH_ERROR user=%s error=%s",
                getattr(
                    user,
                    "username",
                    "unknown",
                ),
                exc,
            )
            return []

    def _primary_group(self, user):
        groups = self._groups(user)

        return (
            groups[0]
            if groups
            else "GENERAL"
        )

    def _load_group_map(self):
        raw = getattr(
            settings,
            "LOGIN_GROUP_REDIRECT_MAP",
            {},
        ) or {}

        normalized = {}

        for group, target in raw.items():
            group_key = (
                str(group)
                .strip()
                .upper()
            )

            target_value = (
                str(target).strip()
                if target
                else ""
            )

            if not target_value:
                logger.warning(
                    "GROUP_MAPPING_SKIPPED group=%s",
                    group_key,
                )
                continue

            normalized[group_key] = target_value

        logger.info(
            "GROUP_MAPPINGS_LOADED count=%s",
            len(normalized),
        )

        return normalized

    def _success(self, is_ajax, url):
        payload = {
            "success": True,
            "redirect": url,
            "timestamp": timezone.now().isoformat(),
        }

        return JsonResponse(payload)
    def _fail(self, request, username, error, is_ajax):
        error_text = str(error)

        logger.warning(
            "LOGIN_ERROR user=%s ip=%s error=%s",
            username,
            self._ip(request),
            error_text,
        )

        payload = {
            "success": False,
            "error": error_text,
            "timestamp": timezone.now().isoformat(),
        }

        if is_ajax:
            response = JsonResponse(
                payload,
                status=403,
            )
            return self._disable_login_caching(response)

        messages.error(
            request,
            error_text,
        )

        response = render(
            request,
            self.template_name,
            {
                "username": "",
                "error": error_text,
                "next": request.POST.get("next", ""),
                "remember_me": False,
            },
            status=403,
        )
        return self._disable_login_caching(response)

    @staticmethod
    def _disable_login_caching(response):
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response

    def _is_ajax(self, request):
        return (
                request.headers.get(
                    "X-Requested-With"
                )
                == "XMLHttpRequest"
        )

    def _ip(self, request):
        xff = request.META.get(
            "HTTP_X_FORWARDED_FOR"
        )

        if xff:
            return (
                xff.split(",")[0]
                .strip()
            )

        x_real_ip = request.META.get(
            "HTTP_X_REAL_IP"
        )

        if x_real_ip:
            return x_real_ip.strip()

        return (
                request.META.get(
                    "REMOTE_ADDR"
                )
                or "unknown"
        )

    def _get_config_safe(self):
        try:
            return (
                SystemConfiguration.objects
                .filter(pk=1)
                .first()
            )

        except Exception as exc:
            logger.exception(
                "CONFIG_LOAD_ERROR error=%s",
                exc,
            )
            return None
