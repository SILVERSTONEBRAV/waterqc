# core/mixins.py
import io
import re
import csv
import json
import logging
import pandas as pd
from docx import Document
from xhtml2pdf import pisa
from django.db import models
from openpyxl import Workbook
from django.db.models import Q
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.http import HttpRequest
from django.db.models import QuerySet
from django.core.paginator import Page
from datetime import datetime, timedelta
from django.core.paginator import Paginator
from core.models import UserPasswordHistory
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse, HttpResponse
from django.contrib.sessions.models import Session
from django.template.loader import select_template
from core.engine.super_user import SuperUserEngine
from core.models import Section, SystemConfiguration
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.list import MultipleObjectMixin
from django.urls import reverse, NoReverseMatch, reverse_lazy
from django.template.loader import get_template, render_to_string
from django.shortcuts import render, redirect, resolve_url, get_object_or_404
from django.core.exceptions import PermissionDenied, FieldDoesNotExist, ValidationError, ObjectDoesNotExist



User = get_user_model()
logger = logging.getLogger(__name__)


class WanjalaMixin(LoginRequiredMixin):

    success_message_create = "Created successfully"
    success_message_update = "Updated successfully"
    success_message_delete = "Deleted successfully"

    enable_events = True
    include_row_html = True
    include_list_html = False
    breadcrumbs = []

    # Keep permission failures closed, while letting anonymous users reach login.
    raise_exception = True

    def handle_no_permission(self):
        """Redirect anonymous requests to login even when permission checks are strict."""
        if not self.request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        return super().handle_no_permission()

    permission_required_create = None
    permission_required_update = None
    permission_required_delete = None
    permission_required_view = None

    last_activity_session_key = "_last_activity"
    filter_icontains = True
    filter_fields = []
    export_fields = None
    export_file_name = None
    export_max_rows = None
    inline_edit_fields = None
    export_date_format = "%Y-%m-%d %H:%M"
    default_paginate_by = None

    def process_request(self, request: HttpRequest):
        now = timezone.now().timestamp()
        request.session[self.last_activity_session_key] = now

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        config = SystemConfiguration.current()

        # =====================================================
        # SUPERUSER HARD BYPASS (CENTRALIZED ENGINE)
        # =====================================================
        if SuperUserEngine.is_superuser(user):
            request.runtime_context = SuperUserEngine.runtime_context(user)

            request.session.update({
                "last_primary_group": "SUPERUSER",
                "last_groups": ["SUPERUSER"],
                "last_module_url": SuperUserEngine.landing_url(),
            })

            # still keep audit light context (no restrictions applied)
            request._cache_timeout_seconds = getattr(config, "cache_timeout_seconds", 300)
            request._audit_log = {
                "user": user.username,
                "ip": self._get_client_ip(request),
                "ts": now,
                "superuser": True,
            }

            return None

        # =====================================================
        # PASSWORD EXPIRATION
        # =====================================================
        pwd_changed = getattr(user, "password_changed_at", None)
        if pwd_changed:
            expiration_days = config.password_expire_days
            if timezone.now() > (pwd_changed + timedelta(days=expiration_days)):
                messages.warning(request, "Your password has expired. Please reset it now.")
                return redirect(resolve_url("accounts:reset_password"))

        # =====================================================
        # DAILY SESSION TIME LIMIT
        # =====================================================
        start = request.session.get("daily_login_start") or now
        total = request.session.get("daily_login_seconds") or 0

        total += max(0, now - start)
        limit = config.daily_login_limit_minutes * 60

        if total > limit:
            logout(request)
            messages.error(request, "You have exceeded your daily login limit.")
            return redirect(resolve_url("accounts:login"))

        request.session["daily_login_start"] = now
        request.session["daily_login_seconds"] = total

        # =====================================================
        # SESSION CONCURRENCY LIMIT
        # =====================================================
        if config.max_concurrent_sessions > 0:
            sessions = Session.objects.filter(expire_date__gte=timezone.now())
            user_sessions = [
                s for s in sessions
                if self._session_belongs_to_user(s, user)
            ]

            if len(user_sessions) > config.max_concurrent_sessions:
                excess = user_sessions[:-config.max_concurrent_sessions]
                for s in excess:
                    logger.info(f"[SessionLimit] Removing session {s.session_key}")
                    s.delete()

        # =====================================================
        # ADAPTIVE MFA
        # =====================================================
        if getattr(config, "adaptive_mfa_enabled", False):
            if getattr(user, "risk_score", 0) >= getattr(config, "adaptive_risk_threshold", 100):
                if not getattr(user, "mfa_verified", False):
                    messages.warning(request, "MFA required for this session.")
                    return redirect(resolve_url("accounts:verify_mfa"))

        # =====================================================
        # FORCE LOGOUT FLAG
        # =====================================================
        if getattr(user, "force_logout", False):
            logout(request)
            messages.warning(request, "Session terminated by system policy.")
            return redirect(resolve_url("accounts:login"))

        # =====================================================
        # AUDIT CONTEXT
        # =====================================================
        request._cache_timeout_seconds = getattr(config, "cache_timeout_seconds", 300)

        if getattr(config, "log_sensitive_actions", False):
            request._audit_log = {
                "user": user.username,
                "ip": self._get_client_ip(request),
                "ts": now,
                "superuser": False,
            }

        return None

    def _ensure_runtime_defaults(self):
        if not hasattr(self, "idle_timeout"):
            self.idle_timeout = getattr(settings, "IDLE_TIMEOUT_SECONDS", 900)

    def build_user_runtime_context(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        # =====================================================
        # SUPERUSER SHORT-CIRCUIT (NO GROUP LOGIC AT ALL)
        # =====================================================
        if SuperUserEngine.is_superuser(user):
            ctx = SuperUserEngine.runtime_context(user)

            request.runtime_context = ctx

            request.session.update({
                "last_primary_group": "SUPERUSER",
                "last_groups": ["SUPERUSER"],
                "last_module_url": ctx.get("default_landing"),
            })

            return ctx

        # =====================================================
        # GROUP NORMALIZATION
        # =====================================================
        groups = [
            g.upper().strip()
            for g in user.groups.values_list("name", flat=True)
            if g
        ]

        primary_group = groups[0] if groups else "GENERAL"

        # =====================================================
        # SETTINGS-DRIVEN GROUP ROUTING MAP
        # =====================================================
        raw_map = getattr(settings, "GROUP_LANDING_PAGES", {}) or {}
        group_map = {str(k).upper().strip(): v for k, v in raw_map.items()}

        # =====================================================
        # SAFE SESSION RESUME ENGINE
        # =====================================================
        def safe_path(value):
            return value if isinstance(value, str) and value.startswith("/") else None

        resume = {
            "last_module_url": safe_path(request.session.get("last_module_url")),
            "last_module_name": request.session.get("last_module_name"),
            "stack": (request.session.get(f"module_stack_{user.id}", []) or [])[-10:],
        }

        # =====================================================
        # LANDING RESOLUTION
        # =====================================================
        def resolve_landing():
            if resume["last_module_url"]:
                return resume["last_module_url"]

            target = group_map.get(primary_group)
            if target:
                try:
                    return reverse(target)
                except NoReverseMatch:
                    pass

            try:
                return reverse("accounts:dashboard")
            except NoReverseMatch:
                return "/"

        # =====================================================
        # NAVIGATION SNAPSHOT
        # =====================================================
        navigation = {
            "current": request.path,
            "last": resume["last_module_url"],
            "has_resume": bool(resume["last_module_url"]),
        }

        # =====================================================
        # FINAL CONTEXT
        # =====================================================
        context = {
            "groups": groups,
            "primary_group": primary_group,
            "resume": resume,
            "navigation": navigation,
            "default_landing": resolve_landing(),
        }

        request.runtime_context = context

        request.session.update({
            "last_primary_group": primary_group,
            "last_groups": groups,
            "last_module_url": request.path if request.path else request.session.get("last_module_url"),
        })

        return context

    def dispatch(self, request, *args, **kwargs):
        self.request = request

        # 1. lifecycle checks
        result = self.process_request(request)
        if result:
            return result

        self.check_idle_timeout()

        # 2. ✅ ONLY trigger export if requested
        export_type = (
                request.GET.get("export")
                or request.GET.get("type")
        )

        if export_type:
            return self.handle_export(request)

        # 3. normal flow
        return super().dispatch(request, *args, **kwargs)

    def paginate_queryset(self, queryset, section=None):

        paginate_by = getattr(self, "default_paginate_by", None)

        if not paginate_by:
            return None, None, queryset, False

        paginator = Paginator(queryset, paginate_by)

        page_number = self.request.GET.get("page", 1)

        page_obj = paginator.get_page(page_number)

        return (
            paginator,
            page_obj,
            page_obj.object_list,
            page_obj.has_other_pages(),
        )

    # ------------------- SESSION / PASSWORD ------------------- #
    def store_password_history(self, user: User):
        """
        Store a snapshot of the user's password to prevent reuse of last N passwords.
        """
        UserPasswordHistory.objects.create(user=user, password_hash=user.password)
        history = UserPasswordHistory.objects.filter(user=user).order_by("-created_at")
        excess_entries = history[self.config.password_history_count:]
        for entry in excess_entries:
            entry.delete()

    @staticmethod
    def validate_password(user: User, new_password: str):
        """
        Validates password according to system configuration and last N history.
        """
        config = SystemConfiguration.current()
        if len(new_password) < config.password_min_length:
            raise ValidationError(f"Minimum length is {config.password_min_length}")
        if config.password_require_digit and not any(c.isdigit() for c in new_password):
            raise ValidationError("Must include a digit")
        if config.password_require_uppercase and not any(c.isupper() for c in new_password):
            raise ValidationError("Must include uppercase letter")
        if config.password_require_lowercase and not any(c.islower() for c in new_password):
            raise ValidationError("Must include lowercase letter")
        if config.password_require_special and not any(c in "!@#$%^&*()_+-=" for c in new_password):
            raise ValidationError("Must include special character")

        recent_passwords = UserPasswordHistory.objects.filter(user=user).order_by("-created_at")[:config.password_history_count]
        for ph in recent_passwords:
            if user.check_password(new_password) or getattr(ph, "check_password_match", lambda x: False)(new_password):
                raise ValidationError(f"Cannot reuse last {config.password_history_count} passwords")

    # ------------------- SESSION UTILITIES ------------------- #
    def _session_belongs_to_user(self, session: Session, user: User) -> bool:
        try:
            return session.get_decoded().get("_auth_user_id") == str(user.id)
        except Exception:
            return False

    def _get_client_ip(self, request: HttpRequest) -> str:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    # ------------------- IDLE TIMEOUT ------------------- #
    def check_idle_timeout(self):
        request = getattr(self, "request", None)
        if not request or not request.user.is_authenticated:
            return

        now = timezone.now().timestamp()

        last = request.session.get(self.last_activity_session_key)
        if not last:
            request.session[self.last_activity_session_key] = now
            return

        config = SystemConfiguration.current()
        idle_timeout = getattr(config, "idle_timeout_minutes", 15) * 60

        elapsed = now - last

        if elapsed > idle_timeout:
            from django.contrib.auth import logout
            from django.shortcuts import redirect
            from django.urls import reverse

            logout(request)
            return redirect(reverse("accounts:login"))

        request.session[self.last_activity_session_key] = now

    # ------------------- PERMISSIONS ------------------- #
    def get_required_permission(self, action=None):
        action = action or getattr(self, "action", "view")
        perm_map = {
            "create": self.permission_required_create,
            "update": self.permission_required_update,
            "delete": self.permission_required_delete,
            "view": self.permission_required_view,
        }
        if perm_map.get(action):
            return perm_map[action]
        if hasattr(self, "model") and self.model:
            opts = self.model._meta
            return {
                "create": f"{opts.app_label}.add_{opts.model_name}",
                "update": f"{opts.app_label}.change_{opts.model_name}",
                "delete": f"{opts.app_label}.delete_{opts.model_name}",
                "view": f"{opts.app_label}.view_{opts.model_name}",
            }.get(action)
        return None


    def check_permission(self, action=None):
        if self.request.user.is_superuser:
            return True
        perm = self.get_required_permission(action)
        if not perm:
            if self.raise_exception:
                raise PermissionDenied(
                    f"No permission is configured for '{action or self.action}'."
                )
            return False
        if not self.request.user.has_perm(perm):
            if self.raise_exception:
                raise PermissionDenied(f"Permission '{perm}' required for '{action}'")
            return False
        return True

    def get_ui_permissions(self):
        user = self.request.user

        def allowed(action):
            permission = self.get_required_permission(action)
            return bool(permission and user.has_perm(permission))

        return {
            "can_create": allowed("create"),
            "can_update": allowed("update"),
            "can_delete": allowed("delete"),
            "can_export": user.has_perm(f"{self.model._meta.app_label}.export_{self.model._meta.model_name}"),
        }

    # ------------------- USER PLANTS ------------------- #
    def get_user_plants(self):
        from t.models import TreatmentPlant  # ✅ move here

        cache_key = f"user_plants_{self.request.user.id}"
        plants = self.request.session.get(cache_key)

        if plants is None:
            qs = TreatmentPlant.objects.all() if self.request.user.is_superuser else TreatmentPlant.objects.filter(
                assigned_users=self.request.user
            )
            plants = list(qs.values("id", "name"))
            self.request.session[cache_key] = plants

        return TreatmentPlant.objects.filter(id__in=[p["id"] for p in plants])

    def filter_by_user_plant(self, qs, plant=None):
        if plant is None:
            plant = self.get_user_plants().first()
        return qs.filter(treatment_plant=plant) if plant and hasattr(qs.model, "treatment_plant") else qs


    def post_inline_edit(self, request):
        """
        Handle inline edits with full permission enforcement using get_required_permission.
        Supports JSON and form POST, type-aware field conversion, ManyToMany,
        ForeignKey resolution, and HTMX response fragments.
        """
        # ------------------- Parse request ------------------- #
        if request.content_type == "application/json":
            try:
                data = json.loads(request.body.decode("utf-8"))
            except json.JSONDecodeError:
                return JsonResponse({"success": False, "message": "Invalid JSON."}, status=400)
            pk = data.get("pk")
            field = data.get("field")
            value = data.get("value")
        else:
            pk = request.POST.get("pk")
            field = request.POST.get("field")
            value = request.POST.get("value")

        if not pk or not field:
            return JsonResponse({"success": False, "message": "Missing 'pk' or 'field'."}, status=400)

        # ------------------- Fetch object ------------------- #
        obj = get_object_or_404(self.model, pk=pk)

        required_perm = self.get_required_permission("update")
        if not request.user.has_perm(required_perm):
            return JsonResponse({"success": False, "message": "Permission denied."}, status=403)

        # ------------------- Editable field check ------------------- #
        protected_fields = ["id", "pk", "created_at", "updated_at"]
        inline_edit_fields = getattr(self, "inline_edit_fields", None)
        if inline_edit_fields is not None:
            if field not in inline_edit_fields:
                return JsonResponse({"success": False, "message": f"Field '{field}' cannot be edited."}, status=403)
        else:
            if field in protected_fields:
                return JsonResponse(
                    {"success": False, "message": f"Field '{field}' is protected and cannot be edited."}, status=403
                )

        # ------------------- Type-aware conversion ------------------- #
        try:
            model_field = obj._meta.get_field(field)
            is_m2m = False

            # ForeignKey
            if isinstance(model_field, models.ForeignKey):
                related_model = model_field.remote_field.model
                try:
                    value = int(value)
                    value = related_model.objects.get(pk=value)
                except (ValueError, TypeError, ObjectDoesNotExist):
                    return JsonResponse({"success": False, "errors": {field: [f"Invalid related object PK: {value}"]}},
                                        status=400)

            # ManyToManyField
            elif isinstance(model_field, models.ManyToManyField):
                related_model = model_field.remote_field.model
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        value = [v.strip() for v in value.split(",") if v.strip()]
                if not isinstance(value, list):
                    return JsonResponse(
                        {"success": False, "errors": {field: ["Expected list of PKs for ManyToManyField"]}}, status=400
                    )

                related_objs = list(related_model.objects.filter(pk__in=value))
                missing = set(map(str, value)) - {str(o.pk) for o in related_objs}
                if missing:
                    return JsonResponse(
                        {"success": False, "errors": {field: [f"Related objects not found: {missing}"]}}, status=400
                    )
                m2m_value = related_objs
                is_m2m = True

            # Other field types
            else:
                # Choices
                if model_field.choices:
                    valid_values = [v for v, _ in model_field.choices]
                    if value not in valid_values:
                        return JsonResponse(
                            {"success": False, "errors": {field: [f"Invalid choice '{value}'. Valid: {valid_values}"]}},
                            status=400
                        )

                # Boolean
                elif isinstance(model_field, models.BooleanField):
                    value = str(value).lower() in ["true", "1", "yes"]

                # Numbers
                elif isinstance(model_field, (models.IntegerField, models.BigIntegerField)):
                    value = int(value)
                elif isinstance(model_field, models.FloatField):
                    value = float(value)
                elif isinstance(model_field, models.DecimalField):
                    from decimal import Decimal, InvalidOperation
                    try:
                        value = Decimal(value)
                    except InvalidOperation:
                        raise ValidationError({field: f"Invalid decimal value: {value}"})

                # Dates
                elif isinstance(model_field, models.DateTimeField):
                    dt = parse_datetime(value)
                    if not dt:
                        raise ValidationError({field: f"Invalid datetime format: {value}"})
                    value = dt
                elif isinstance(model_field, models.DateField):
                    dt = parse_datetime(value)
                    if not dt:
                        raise ValidationError({field: f"Invalid date format: {value}"})
                    value = dt.date()

                # JSONField
                elif isinstance(model_field, models.JSONField):
                    if isinstance(value, str):
                        value = json.loads(value)

                # CharField
                elif isinstance(model_field, models.CharField) and value is not None:
                    value = str(value)

        except FieldDoesNotExist:
            return JsonResponse({"success": False, "message": f"Field '{field}' does not exist."}, status=400)
        except (ValueError, TypeError, ValidationError, json.JSONDecodeError) as e:
            return JsonResponse({"success": False, "errors": {field: [str(e)]}}, status=400)

        # ------------------- Save object ------------------- #
        try:
            if is_m2m:
                getattr(obj, field).set(m2m_value)
            else:
                setattr(obj, field, value)
                obj.full_clean()
                obj.save(update_fields=[field])
        except ValidationError as e:
            return JsonResponse({"success": False, "errors": e.message_dict}, status=400)
        response_payload = {
            "success": True,
            "object_id": obj.pk,
            "row_html": row_html,
            "list_html": list_html,
            "field": field,
            "value": value if not is_m2m else [o.pk for o in m2m_value],
        }

        response = JsonResponse(response_payload)

        # HTMX triggers
        if hasattr(self, "attach_hx_trigger"):
            self.attach_hx_trigger(response)

        response["HX-Trigger"] = json.dumps({
            "inlineEditSuccess": {
                "object_id": obj.pk,
                "field": field,
                "value": response_payload["value"]
            }
        })

        return response

    # ------------------- CONTEXT ------------------- #
    def get_breadcrumbs(self):
        if getattr(self, "breadcrumbs", []):
            return self.breadcrumbs
        if hasattr(self, "model") and self.model:
            return [{"title": self.model._meta.verbose_name_plural.title(), "url": self.get_success_url()}]
        return []

    # ------------------- HTMX / AJAX ------------------- #
    def is_htmx(self):
        return self.request.headers.get("HX-Request") == "true"

    def is_ajax(self):
        return self.request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def is_partial(self):
        return self.is_htmx() or self.is_ajax()

    def get_partial_template(self):
        if self.action == "create" and self.create_partial_template:
            return self.create_partial_template
        if self.action == "update" and self.update_partial_template:
            return self.update_partial_template
        return self.partial_template_name or getattr(self, "template_name", None)

    # ------------------- FORM HANDLING ------------------- #
    def before_save(self, form): pass
    def after_save(self, obj):
        action = getattr(self, "action", None)
        messages.success(self.request, {
            "create": self.success_message_create,
            "update": self.success_message_update,
        }.get(action, self.success_message_create))
        self.broadcast_event(f"{action}_{self.model.__name__}", {"object_id": obj.pk, "snapshot": str(obj)})
        logger.info(f"[Audit] {self.request.user} {action} {self.model.__name__} ID={obj.pk}")


    # ------------------- DELETE HANDLING ------------------- #
    def before_delete(self, obj): pass

    def after_delete(self, obj_id):
        messages.success(self.request, self.success_message_delete)
        self.broadcast_event(f"delete_{self.model.__name__}", {"object_id": obj_id})
        logger.info(f"[Audit] {self.request.user} deleted {self.model.__name__} ID={obj_id}")

    def delete(self, request, *args, **kwargs):
        self.action = "delete"
        self.check_permission(self.action)
        self.object = self.get_object()
        obj_id = self.object.pk
        self.before_delete(self.object)
        if request.user.is_superuser:
            from core.engine.superuser_authorization import force_delete_objects

            force_delete_objects([self.object], actor=request.user)
        else:
            self.object.delete()
        self.after_delete(obj_id)
        if self.is_partial():
            response = self.json_response(self.build_response(success=True, action="delete", object_id=obj_id))
            self.attach_hx_trigger(response)
            return response
        return HttpResponse(status=204)

    # ------------------- JSON / HX RESPONSES ------------------- #
    def build_response(self, **kwargs):
        return {
            "success": kwargs.get("success", True),
            "message": kwargs.get("message", getattr(self, "success_message_create", "Operation successful")),
            "action": kwargs.get("action"),
            "object_id": kwargs.get("object_id"),
            "row_html": kwargs.get("row_html"),
            "list_html": kwargs.get("list_html"),
            "errors": kwargs.get("errors"),
            "meta": kwargs.get("meta", {}),
        }

    def json_response(self, payload, status=200):
        return JsonResponse(payload, status=status)

    def attach_hx_trigger(self, response):
        events = self.request.session.pop("_broadcast_events", [])
        if events:
            triggers = getattr(response, "headers", {})
            existing = json.loads(triggers.get("HX-Trigger", "{}")) if "HX-Trigger" in triggers else {}
            combined = {**existing, **{e["event"]: e["payload"] for e in events}}
            response["HX-Trigger"] = json.dumps(combined)

    def broadcast_event(self, name, payload=None, namespace=None):
        if self.enable_events:
            events = self.request.session.get("_broadcast_events", [])
            event_name = f"{namespace}:{name}" if namespace else name
            events.append({"event": event_name, "payload": payload or {}})
            self.request.session["_broadcast_events"] = events


    def render_row(request, entry, obj=None, state="view"):
        html = render_to_string("core/row/dynamic_row.html", {
            "obj": obj,
            "fields": entry.config.get("fields_config") or [],
            "state": state
        }, request=request)

        return JsonResponse({"html": html})

    def render_list(self):
        """
        Render full list (used for refresh / bulk updates).
        """

        template_key = self.list_template_name or "list"

        context = self.get_context_data()

        html = self._render_to_string_safe(template_key, context)

        return html  # ✅ string-safe

    # ------------------- URL / Success ------------------- #
    def get_success_url(self):
        try:
            return super().get_success_url()
        except Exception:
            return reverse_lazy(
                f"{self.model._meta.app_label}:{self.model._meta.model_name}_list"
            )

    # ------------------- WORKFLOW / TRANSITION ------------------- #
    def handle_transition(self, obj, action, template=None, flow_instance=None, obj_key="object"):
        flow_instance = flow_instance or getattr(obj, "flow_class", None)
        template = template or getattr(self, "row_template_name")
        try:
            action_lower = action.lower()
            if flow_instance:
                method_name = f"_{action_lower}_manual"
                if hasattr(flow_instance, method_name):
                    getattr(flow_instance, method_name)(getattr(obj, "vf_process", None), self.request.user)
                else:
                    obj.transition_to(action, performed_by=self.request.user)
            else:
                obj.transition_to(action, performed_by=self.request.user)
            self.broadcast_event(f"{obj.__class__.__name__.lower()}:transitioned", {"id": obj.pk, "action": action_lower})
            if self.is_partial():
                html = render_to_string(template, {obj_key: obj}, request=self.request)
                return HttpResponse(html)
            return redirect(obj.get_absolute_url() if hasattr(obj, "get_absolute_url") else self.get_success_url())
        except Exception as e:
            if self.is_partial():
                return JsonResponse({"success": False, "message": str(e)}, status=500)
            raise

    def get_export_queryset(self):
        """
        Uses SAME logic as UI queryset.
        Guarantees consistency between UI & export.
        """
        qs = self.get_queryset()

        if self.export_max_rows:
            qs = qs[:self.export_max_rows]

        return qs

    # ----------------- FIELD RESOLUTION ----------------- #
    def get_export_fields(self):
        """
        Dynamically resolve exportable fields.
        Excludes reverse relations automatically.
        """

        if self.export_fields:
            return self.export_fields

        return [
            f.name
            for f in self.model._meta.get_fields()
            if (
                    hasattr(f, "attname") and
                    not f.many_to_many and
                    not f.one_to_many
            )
        ]

    # ----------------- VALUE FORMATTING ----------------- #
    def format_export_value(self, obj, field):
        val = getattr(obj, field, None)

        if val is None:
            return ""

        # FK / object
        if hasattr(val, "__str__"):
            return str(val)

        # Date / datetime
        if hasattr(val, "strftime"):
            return val.strftime(self.export_date_format)

        # JSON
        if isinstance(val, (dict, list)):
            return json.dumps(val)

        return str(val)

    # ----------------- GENERIC FILE NAME ----------------- #
    def get_export_file_name(self, ext):
        base = self.export_file_name or self.model._meta.model_name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{base}_{timestamp}.{ext}"

    # ----------------- CSV EXPORT ----------------- #
    def export_csv(self):
        qs = self.get_export_queryset()
        fields = self.get_export_fields()

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{self.get_export_file_name("csv")}"'

        writer = csv.writer(response)
        writer.writerow(fields)

        for obj in qs:
            writer.writerow([self.format_export_value(obj, f) for f in fields])

        return response

    # ----------------- EXCEL EXPORT ----------------- #
    def export_excel(self):
        qs = self.get_export_queryset()
        fields = self.get_export_fields()

        wb = Workbook()
        ws = wb.active
        ws.title = self.model._meta.verbose_name_plural.title()

        ws.append(fields)

        for obj in qs:
            ws.append([self.format_export_value(obj, f) for f in fields])

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{self.get_export_file_name("xlsx")}"'

        wb.save(response)
        return response

    # ----------------- DOCX EXPORT ----------------- #
    def export_docx(self):
        qs = self.get_export_queryset()
        fields = self.get_export_fields()

        doc = Document()
        table = doc.add_table(rows=1, cols=len(fields))

        for i, f in enumerate(fields):
            table.rows[0].cells[i].text = f

        for obj in qs:
            row = table.add_row().cells
            for i, f in enumerate(fields):
                row[i].text = self.format_export_value(obj, f)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        response["Content-Disposition"] = f'attachment; filename="{self.get_export_file_name("docx")}"'

        doc.save(response)
        return response

    # ----------------- PDF EXPORT ----------------- #
    def export_pdf(self):
        qs = self.get_export_queryset()
        fields = self.get_export_fields()
        rows = [
            [self.format_export_value(obj, field) for field in fields]
            for obj in qs
        ]

        context = {
            "rows": rows,
            "fields": fields,
            "title": self.model._meta.verbose_name_plural.title()
        }

        html = render_to_string("core/partials/export_pdf.html", context)

        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{self.get_export_file_name("pdf")}"'

        pisa.CreatePDF(io.BytesIO(html.encode("utf-8")), dest=response)
        return response

    def handle_export(self, request):
        export_type = request.GET.get("export")

        if not export_type:
            return None

        export_map = {
            "csv": self.export_csv,
            "xlsx": self.export_excel,
            "docx": self.export_docx,
            "pdf": self.export_pdf,
        }

        handler = export_map.get(export_type.lower())

        return handler() if handler else None

    def htmx_delete(self, request, pk):
        from django.views.decorators.csrf import csrf_exempt

        obj = get_object_or_404(self.model, pk=pk)
        if hasattr(self, "check_permission"):
            self.check_permission("delete")
        if request.user.is_superuser:
            from core.engine.superuser_authorization import force_delete_objects

            force_delete_objects([obj], actor=request.user)
        else:
            obj.delete()
        if request.headers.get("HX-Request"):
            return HttpResponse(status=204)
        return redirect(getattr(self, "success_url", "/"))

    # core/mixins.py (inside WanjalaMixin)

    # ------------------- JSON FORM SUPPORT ------------------- #
    def get_json_data(self):

        if self.request.content_type == "application/json":
            try:
                return json.loads(self.request.body.decode("utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def get_form_kwargs(self):

        kwargs = super().get_form_kwargs()
        if self.request.method in ["POST", "PUT", "PATCH"]:
            json_data = self.get_json_data()
            if json_data:
                kwargs["data"] = json_data
        return kwargs

    def form_valid(self, form):
        if hasattr(form, "instance"):
            self.action = "update" if form.instance.pk else "create"
            self.check_permission(self.action)
            self.before_save(form)

            self.object = form.save()

            self.after_save(self.object)

            # HTMX / AJAX response
            if self.is_partial():
                html = render_to_string(
                    self.row_template_name,
                    {"object": self.object},
                    request=self.request
                )
                return JsonResponse({
                    "id": self.object.pk,
                    "html": html,
                })

            return super().form_valid(form)

        return super().form_valid(form)

    def get_queryset(self):
        """
        Safe queryset resolver that works across:
        - View
        - TemplateView
        - ListView
        - custom mixin chains
        """

        # 1. Try parent queryset safely
        parent = getattr(super(), "get_queryset", None)

        if callable(parent):
            try:
                qs = parent()
            except Exception:
                qs = None
        else:
            qs = None

        # 2. fallback to model queryset
        if qs is None:
            model = getattr(self, "model", None)
            if model is None:
                raise ImproperlyConfigured(
                    f"{self.__class__.__name__} must define 'model' or override get_queryset()"
                )
            qs = model.objects.all()

        # 3. OPTIONAL: filtering logic (your existing logic preserved safely)
        model = qs.model
        meta = model._meta
        params = self.request.GET.copy()

        field_map = {f.name: f for f in meta.get_fields() if hasattr(f, "attname")}

        for param, value in params.items():
            if not value or param in ["page", "search", "ordering", "export"]:
                continue

            field = field_map.get(param)
            if not field:
                continue

            try:
                lookup = param

                if isinstance(field, (models.CharField, models.TextField)):
                    lookup = f"{param}__icontains"

                elif isinstance(field, models.ForeignKey):
                    lookup = f"{param}_id"

                elif isinstance(field, models.BooleanField):
                    value = str(value).lower() in ["true", "1", "yes"]

                qs = qs.filter(**{lookup: value})

            except Exception:
                continue

        # 4. SEARCH
        search = params.get("search")
        if search:
            query = Q()
            for f in meta.get_fields():
                if isinstance(f, (models.CharField, models.TextField)):
                    query |= Q(**{f"{f.name}__icontains": search})
            qs = qs.filter(query)

        # 5. OPTIMIZATION
        fk_fields = [f.name for f in meta.fields if isinstance(f, models.ForeignKey)]
        if fk_fields:
            qs = qs.select_related(*fk_fields)

        m2m_fields = [f.name for f in meta.many_to_many]
        if m2m_fields:
            qs = qs.prefetch_related(*m2m_fields)

        # 6. ORDERING
        ordering = params.get("ordering")
        if ordering:
            try:
                qs = qs.order_by(ordering)
            except Exception:
                pass

        return qs.distinct()

    def _is_superuser(self, user):
        return SuperUserEngine.is_superuser(user)
