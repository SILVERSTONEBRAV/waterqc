import logging
from django.views import View
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import resolve_url, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.core.cache import cache
from django.contrib.sessions.models import Session
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class LogoutView(LoginRequiredMixin, View):

    def get(self, request):
        user = request.user
        session_key = request.session.session_key
        username = getattr(user, "username", "unknown")
        ip = self._ip(request)
        ts = timezone.now().isoformat()

        if not user or not user.is_authenticated:
            return redirect(self._safe_redirect())

        # 1. Audit
        self._audit_logout(user, request, session_key, ip, ts)

        # 2. Broadcast global logout
        self._broadcast_global_logout(user, session_key)

        # 3. Terminate all sessions
        self._terminate_all_user_sessions(user)

        # 4. JWT invalidation hook
        self._invalidate_jwt_tokens(user)

        # 5. Websocket notification hook
        self._notify_websocket_clients(user)

        # 6. Clear runtime session
        self._clear_runtime_session(request)

        # 7. Flush session
        self._flush_session(request)

        # 8. Django auth logout
        auth_logout(request)

        # 9. Save session to flush cookies immediately
        request.session.save()

        logger.info(
            "LOGOUT_SUCCESS user=%s ip=%s session=%s time=%s global=True",
            username,
            ip,
            session_key,
            ts,
        )

        # Return JSON if AJAX, else redirect
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True, "redirect": str(self._safe_redirect())})

        return redirect(self._safe_redirect())

    # --- helpers unchanged ---
    def _terminate_all_user_sessions(self, user):
        try:
            if not user or not user.id:
                return
            sessions = Session.objects.filter(expire_date__gte=timezone.now())
            for session in sessions:
                try:
                    data = session.get_decoded()
                    if str(data.get("_auth_user_id")) == str(user.id):
                        session.delete()
                except Exception:
                    continue
        except Exception as e:
            logger.error("SESSION_GLOBAL_LOGOUT_ERROR user=%s err=%s", getattr(user, "username", "unknown"), str(e))

    def _broadcast_global_logout(self, user, session_key):
        try:
            key = f"logout_signal:{user.id}"
            payload = {
                "event": "GLOBAL_LOGOUT",
                "user_id": user.id,
                "username": getattr(user, "username", None),
                "session": session_key,
                "timestamp": timezone.now().timestamp(),
                "reason": "user_logout",
            }
            cache.set(key, payload, timeout=300)
        except Exception as e:
            logger.error("LOGOUT_BROADCAST_ERROR user=%s err=%s", getattr(user, "username", "unknown"), str(e))

    def _flush_session(self, request):
        try:
            request.session.flush()
        except Exception:
            request.session.clear()

    def _clear_runtime_session(self, request):
        keys = [
            "authenticated_user_id", "authenticated_username", "last_login_ts",
            "last_primary_group", "resolved_login_group", "resolved_login_target",
            "last_module", "last_url", "last_visited_url", "login_context",
        ]
        for key in keys:
            try:
                request.session.pop(key, None)
            except Exception:
                pass

    def _audit_logout(self, user, request, session_key, ip, ts):
        try:
            logger.info(
                "AUDIT_LOGOUT | user=%s | id=%s | ip=%s | session=%s | time=%s | ua=%s",
                getattr(user, "username", "unknown"),
                getattr(user, "id", None),
                ip,
                session_key,
                ts,
                request.META.get("HTTP_USER_AGENT", ""),
            )
        except Exception:
            pass

    def _safe_redirect(self):
        return reverse_lazy("accounts:login")

    def _ip(self, request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    def _invalidate_jwt_tokens(self, user):
        pass

    def _notify_websocket_clients(self, user):
        pass
