from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import resolve_url
from asgiref.sync import iscoroutinefunction, markcoroutinefunction

from core.engine.superuser_authorization import (
    bind_request_user,
    reset_request_user,
)


class SuperuserAuthorizationContextMiddleware:
    """Scope elevated permissions and hard-delete behavior to one request."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._is_async = iscoroutinefunction(get_response)
        if self._is_async:
            markcoroutinefunction(self)

    def __call__(self, request):
        if self._is_async:
            return self.__acall__(request)
        return self.__scall__(request)

    def _bind(self, request):
        token = bind_request_user(getattr(request, "user", None))
        user = getattr(request, "user", None)
        path_parts = [
            part.casefold()
            for part in request.path_info.strip("/").split("/")
            if part
        ]
        deletion_markers = {"delete", "remove", "purge", "destroy", "erase"}
        deletion_intent = (
            request.method.upper() == "DELETE"
            or any(
                part == marker or part.startswith((marker + "-", marker + "_"))
                for part in path_parts
                for marker in deletion_markers
            )
        )
        if (
            deletion_intent
            and getattr(user, "is_authenticated", False)
            and not (
                getattr(user, "is_active", False)
                and getattr(user, "is_superuser", False)
            )
        ):
            from django.http import HttpResponseForbidden

            return token, HttpResponseForbidden(
                "Only an active superuser can delete records."
            )
        return token, None

    def __scall__(self, request):
        token, denied = self._bind(request)
        try:
            if denied is not None:
                return denied
            return self.get_response(request)
        finally:
            reset_request_user(token)

    async def __acall__(self, request):
        token, denied = self._bind(request)
        try:
            if denied is not None:
                return denied
            return await self.get_response(request)
        finally:
            reset_request_user(token)


class AnonymousForbiddenRedirectMiddleware:
    """Send anonymous users to login when a protected endpoint returns 403."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code != 403:
            return response

        user = getattr(request, "user", None)
        if user is None or user.is_authenticated:
            return response

        login_url = resolve_url(settings.LOGIN_URL)
        if request.path_info in {login_url, "/login/"}:
            return response

        return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)


class SingleDeviceSessionMiddleware:
    """
    Enforce single PC/device session per user account.
    If an account is opened on another computer, any prior session is terminated.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            path = request.path_info
            exempt_paths = (
                "/accounts/login/",
                "/accounts/logout/",
                "/login/",
                "/logout/",
                "/static/",
                "/manifest.json",
                "/sw.js",
            )
            if not any(path.startswith(p) for p in exempt_paths):
                current_session_key = getattr(request.session, "session_key", None)
                if current_session_key:
                    from django.core.cache import cache
                    import logging

                    logger = logging.getLogger(__name__)
                    cache_key = f"active_user_session:{user.pk}"
                    active_session_key = cache.get(cache_key)

                    if active_session_key is None:
                        timeout = getattr(settings, "SESSION_COOKIE_AGE", 28800)
                        cache.set(cache_key, current_session_key, timeout=timeout)
                        active_session_key = current_session_key

                    if active_session_key and active_session_key != current_session_key:
                        logger.warning(
                            "CONCURRENT_LOGIN_DETECTED: user=%s session=%s active=%s - logging out obsolete session",
                            user.username,
                            current_session_key,
                            active_session_key,
                        )
                        from django.contrib.auth import logout as auth_logout
                        from django.http import JsonResponse
                        from django.shortcuts import redirect

                        auth_logout(request)
                        try:
                            request.session.flush()
                        except Exception:
                            pass

                        if (
                            request.headers.get("X-Requested-With") == "XMLHttpRequest"
                            or "application/json" in request.headers.get("Accept", "")
                        ):
                            return JsonResponse(
                                {
                                    "authenticated": False,
                                    "error": "concurrent_login",
                                    "message": "Your account was logged in from another computer. You have been logged out.",
                                    "redirect": "/accounts/login/?reason=concurrent_login",
                                },
                                status=401,
                            )

                        return redirect("/accounts/login/?reason=concurrent_login")

        return self.get_response(request)
