import logging
from threading import local
from django.contrib.auth import get_user_model
from django.urls import Resolver404, resolve
from django.utils.deprecation import MiddlewareMixin
from django.utils.timezone import now
from .models import AuditLogEntry, UserActivity

logger = logging.getLogger(__name__)
User = get_user_model()

_thread_locals = local()

def get_current_user():
    return getattr(_thread_locals, "user", None)

def set_current_user(user):
    _thread_locals.user = user

class UserActivityLoggingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        set_current_user(None)
        request._start_time = now()

        if not hasattr(request, "user") or not request.user.is_authenticated:
            return

        set_current_user(request.user)

        try:
            action = self.get_action_from_request(request)

            audit_entry = self.log_audit_entry(
                request,
                action,
                "in_progress",
                {},
            )

            request._audit_entry_id = audit_entry.pk

            self.log_user_activity(
                request,
                audit_entry,
                True,
            )

        except Exception:
            logger.exception("audit_create_failed")

    def process_response(self, request, response):
        try:
            if hasattr(request, "user") and request.user.is_authenticated:
                action = self.get_action_from_request(request)

                status = "success" if response.status_code < 400 else "failure"

                self.update_audit_entry(
                    request,
                    action,
                    status,
                    self.get_additional_data(request, response),
                )
        except Exception:
            logger.exception("audit_update_failed")
        finally:
            set_current_user(None)
        return response

    def process_exception(self, request, exception):
        try:
            if hasattr(request, "user") and request.user.is_authenticated:
                action = self.get_action_from_request(request)

                self.update_audit_entry(
                    request,
                    action,
                    "failure",
                    {
                        "exception": str(exception),
                        "exception_type": exception.__class__.__name__,
                    },
                )
        except Exception:
            logger.exception("audit_exception_failed")
        return None

    def log_user_activity(self, request, audit_entry, successful_attempt):
        try:
            UserActivity.objects.create(
                user=request.user,
                audit_entry=audit_entry,
                ip_address=self.get_client_ip(request),
                timestamp=now(),
                successful_attempt=successful_attempt,
                device=self.get_device_info(request),
                user_agent=self.get_user_agent(request),
                activity_type=self.get_activity_type(request),
                duration=self.get_activity_duration(request),
                location=self.get_location(request),
            )
        except Exception:
            logger.exception("user_activity_failed")

    def log_audit_entry(self, request, action, result_status, additional_data):
        return AuditLogEntry.objects.create(
            user=request.user,
            action=action,
            result_status=result_status,
            timestamp=now(),
            ip_address=self.get_client_ip(request),
            device=self.get_device_info(request),
            user_agent=self.get_user_agent(request),
            location=self.get_location(request),
            additional_data=additional_data,
            description=self.get_description(request),
        )

    def update_audit_entry(self, request, action, result_status, additional_data):
        entry = (
            AuditLogEntry.objects
            .filter(user=request.user, action=action, result_status="in_progress")
            .order_by("-timestamp")
            .first()
        )

        if not entry:
            return

        entry.result_status = result_status
        entry.ip_address = self.get_client_ip(request)
        entry.device = self.get_device_info(request)
        entry.user_agent = self.get_user_agent(request)
        entry.location = self.get_location(request)
        entry.additional_data = additional_data
        entry.description = self.get_description(request)

        entry.save(
            update_fields=[
                "result_status",
                "ip_address",
                "device",
                "user_agent",
                "location",
                "additional_data",
                "description",
            ]
        )

    def get_client_ip(self, request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    def get_device_info(self, request):
        ua = request.META.get("HTTP_USER_AGENT", "")
        if not ua:
            return ""
        ua = ua.lower()
        if "mobile" in ua or "android" in ua or "iphone" in ua:
            return "mobile"
        if "tablet" in ua or "ipad" in ua:
            return "tablet"
        return "desktop"

    def get_user_agent(self, request):
        return request.META.get("HTTP_USER_AGENT", "")

    def get_action_from_request(self, request):
        try:
            match = resolve(request.path_info)
            app = match.app_name or "unknown"
            name = match.url_name or "unknown"
            return f"{app}.{name}"
        except Resolver404:
            return f"unresolved:{request.path}"
        except Exception:
            logger.exception("resolve_failed")
            return f"unknown:{request.path}"

    def get_additional_data(self, request, response):
        return {
            "method": request.method,
            "path": request.path,
            "full_path": request.get_full_path(),
            "status_code": response.status_code,
            "query_params": dict(request.GET),
        }

    def get_activity_type(self, request):
        return request.method

    def get_activity_duration(self, request):
        start = getattr(request, "_start_time", None)
        if not start:
            return None
        try:
            return (now() - start).total_seconds()
        except Exception:
            return None

    def get_location(self, request):
        return "Unknown"

    def get_description(self, request):
        username = getattr(request.user, "username", "Anonymous")
        return f"{username} {request.method} {request.path}"