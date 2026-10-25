"""Request-scoped superuser authorization and unrestricted hard deletion.

The override is deliberately tied to an authenticated, active superuser in the
current request (or to an explicit ``superuser_authority`` context). It does
not change FK behavior for ordinary requests, migrations, or background jobs.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from types import MethodType
from typing import Iterable

from django.apps import apps
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import router, transaction
from django.db.models import Model
from django.db.models.deletion import CASCADE, DO_NOTHING, PROTECT, RESTRICT
from django.db.models.query import QuerySet

from core.engine.super_user import SuperUserEngine


_DJANGO_QUERYSET_DELETE = QuerySet.delete
_PROTECTIVE_HANDLERS = (PROTECT, RESTRICT, DO_NOTHING)

_request_user: ContextVar[object | None] = ContextVar(
    "current_request_user", default=None
)
_authority_user: ContextVar[object | None] = ContextVar(
    "superuser_authority_user", default=None
)
_system_delete_allowed: ContextVar[frozenset[str]] = ContextVar(
    "system_delete_allowed", default=frozenset()
)


def _is_active_superuser(user) -> bool:
    return bool(
        SuperUserEngine.is_superuser(user)
        and getattr(user, "is_active", False)
    )


def current_request_user():
    return _request_user.get()


def has_superuser_authority(user=None) -> bool:
    user = user if user is not None else _authority_user.get() or _request_user.get()
    return _is_active_superuser(user)


def _require_exclusive_delete_authority(model=None) -> None:
    """Reserve request-initiated record deletion for active superusers."""
    # A few framework maintenance hooks must prune their own operational
    # records during an otherwise ordinary request (for example, django-axes
    # expiring old login attempts). This narrowly scoped context never grants
    # superuser permissions or changes protective FK behavior.
    if model is not None and model._meta.label_lower in _system_delete_allowed.get():
        return

    user = _request_user.get()
    if user is not None and not _is_active_superuser(user):
        raise PermissionDenied("Only an active superuser can delete records.")


def bind_request_user(user):
    """Bind the request principal, including anonymous users, until response."""
    return _request_user.set(user)


def reset_request_user(token) -> None:
    _request_user.reset(token)


@contextmanager
def system_delete_authority(*models):
    """Allow housekeeping to delete only its explicitly listed model records."""
    allowed = frozenset(
        model if isinstance(model, str) else model._meta.label_lower
        for model in models
    )
    token = _system_delete_allowed.set(allowed)
    try:
        yield
    finally:
        _system_delete_allowed.reset(token)


@contextmanager
def superuser_authority(actor):
    """Temporarily authorize an explicit superuser operation."""
    if not _is_active_superuser(actor):
        raise PermissionDenied("Only an active superuser can perform this action.")

    request_token = _request_user.set(actor)
    authority_token = _authority_user.set(actor)
    try:
        yield
    finally:
        _authority_user.reset(authority_token)
        _request_user.reset(request_token)


def force_delete_objects(objects: Iterable[Model], *, actor) -> int:
    """Hard-delete objects and every FK-dependent record for a superuser.

    Django's Collector performs the traversal, ordering, signal dispatch, and
    database writes. Its request-scoped on_delete handlers are temporarily
    treated as CASCADE handlers, including PROTECT, RESTRICT, and DO_NOTHING.
    """
    if not _is_active_superuser(actor):
        raise PermissionDenied("Only an active superuser can force-delete records.")

    objects = list(objects)
    if not objects:
        return 0

    database = objects[0]._state.db or router.db_for_write(objects[0].__class__)
    if any(
        (obj._state.db or router.db_for_write(obj.__class__)) != database
        for obj in objects
    ):
        raise ValueError("A forced deletion must use one database.")

    grouped: dict[type[Model], list[object]] = {}
    for obj in objects:
        grouped.setdefault(obj.__class__, []).append(obj)

    deleted = 0
    ca_roots = [obj for obj in objects if obj._meta.app_label == "ca"]
    root_labels = [str(obj)[:500] for obj in ca_roots]
    root_ids = [str(obj.pk) for obj in ca_roots]
    root_model = ca_roots[0]._meta.label if ca_roots else ""
    with superuser_authority(actor), transaction.atomic(using=database):
        for model, instances in grouped.items():
            deleted_count, _ = (
                model._base_manager.db_manager(database)
                .filter(pk__in=[instance.pk for instance in instances])
                .delete()
            )
            deleted += deleted_count
        if ca_roots and root_model.lower() != "ca.chemicalsuperuserpurgeaudit":
            try:
                PurgeAudit = apps.get_model("ca", "ChemicalSuperuserPurgeAudit")
                PurgeAudit.objects.using(database).create(
                    actor=actor,
                    root_model=root_model,
                    root_ids=root_ids,
                    root_labels=root_labels,
                    deleted_counts={"roots": len(ca_roots), "total": deleted},
                )
            except LookupError:
                # Keep hard deletion functional during initial migrations,
                # before the detached audit model is installed.
                pass
    return deleted


class _SuperuserAwareDeleteHandler:
    """Keep normal on_delete semantics, cascade inside superuser requests."""

    _superuser_aware_delete_handler = True

    def __init__(self, original):
        self.original = original
        if getattr(original, "lazy_sub_objs", False):
            self.lazy_sub_objs = True

    def __call__(self, collector, field, sub_objs, using):
        if has_superuser_authority() and any(
            self.original is handler for handler in _PROTECTIVE_HANDLERS
        ):
            return CASCADE(collector, field, sub_objs, using)
        return self.original(collector, field, sub_objs, using)

    def __eq__(self, other):
        if (
            has_superuser_authority()
            and any(self.original is handler for handler in _PROTECTIVE_HANDLERS)
            and other is self.original
        ):
            return False
        return self.original == other

    def deconstruct(self):
        original_deconstruct = getattr(self.original, "deconstruct", None)
        if callable(original_deconstruct):
            return original_deconstruct()
        return (
            f"{getattr(self.original, '__module__', self.original.__class__.__module__)}."
            f"{getattr(self.original, '__qualname__', self.original.__class__.__qualname__)}",
            (),
            {},
        )


def _install_superuser_delete_handlers() -> None:
    for model in apps.get_models(include_auto_created=True):
        for field in model._meta.local_fields:
            if not field.is_relation or not (
                field.many_to_one or field.one_to_one
            ):
                continue
            remote = field.remote_field
            handler = getattr(remote, "on_delete", None)
            if (
                not callable(handler)
                or handler is CASCADE
                or getattr(handler, "_superuser_aware_delete_handler", False)
            ):
                continue
            remote.on_delete = _SuperuserAwareDeleteHandler(handler)

    # Hide the runtime wrapper from migration state. The model field continues
    # to deconstruct to its original on_delete function, so this authorization
    # hook never creates schema migrations.
    from django.db.models import ForeignKey

    original_deconstruct = ForeignKey.deconstruct
    if getattr(original_deconstruct, "_superuser_deconstruct_handler", False):
        return

    @wraps(original_deconstruct)
    def deconstruct(field):
        name, path, args, kwargs = original_deconstruct(field)
        on_delete = kwargs.get("on_delete")
        if isinstance(on_delete, _SuperuserAwareDeleteHandler):
            kwargs["on_delete"] = on_delete.original
        return name, path, args, kwargs

    deconstruct._superuser_deconstruct_handler = True
    ForeignKey.deconstruct = deconstruct


def _install_superuser_model_delete_handlers() -> None:
    """Bypass model-level append-only/soft-delete guards for superusers."""
    for model in apps.get_models(include_auto_created=False):
        original = getattr(model, "delete", None)
        if (
            original is None
            or original is Model.delete
            or getattr(original, "_superuser_delete_handler", False)
        ):
            continue

        @wraps(original)
        def authorized_delete(self, *args, __original=original, **kwargs):
            if has_superuser_authority():
                using = kwargs.get("using", args[0] if args else None)
                keep_parents = kwargs.get(
                    "keep_parents", args[1] if len(args) > 1 else False
                )
                return Model.delete(self, using=using, keep_parents=keep_parents)
            _require_exclusive_delete_authority(self.__class__)
            return __original(self, *args, **kwargs)

        authorized_delete._superuser_delete_handler = True
        setattr(model, "delete", authorized_delete)


def _install_superuser_queryset_delete_handlers() -> None:
    """Make custom soft-delete QuerySets honor superuser hard-delete intent."""
    queryset_classes = set()
    pending = [QuerySet]
    while pending:
        queryset_class = pending.pop()
        if queryset_class in queryset_classes:
            continue
        queryset_classes.add(queryset_class)
        pending.extend(queryset_class.__subclasses__())

    for model in apps.get_models(include_auto_created=True):
        for manager in model._meta.managers:
            queryset_classes.add(getattr(manager, "_queryset_class", QuerySet))

    for queryset_class in queryset_classes:
        original = getattr(queryset_class, "delete", None)
        if (
            original is None
            or getattr(original, "_superuser_delete_handler", False)
        ):
            continue

        @wraps(original)
        def authorized_queryset_delete(
            self, *args, __original=original, **kwargs
        ):
            if has_superuser_authority():
                return _DJANGO_QUERYSET_DELETE(self, *args, **kwargs)
            _require_exclusive_delete_authority(self.model)
            return __original(self, *args, **kwargs)

        authorized_queryset_delete._superuser_delete_handler = True
        setattr(queryset_class, "delete", authorized_queryset_delete)


def _install_axes_housekeeping_delete_authority() -> None:
    """Permit django-axes' automatic expiry cleanup during login/logout."""
    try:
        from axes.handlers.database import AxesDatabaseHandler
    except ImportError:
        return

    # These operations are invoked internally by django-axes while recording
    # authentication events. They only prune expired attempts or excess
    # failure logs; admin/manual reset methods remain superuser-only.
    from axes.models import AccessAttempt, AccessFailureLog

    method_models = {
        "clean_expired_user_attempts": (AccessAttempt,),
        "reset_user_attempts": (AccessAttempt,),
        "remove_out_of_limit_failure_logs": (AccessFailureLog,),
    }
    for method_name, allowed_models in method_models.items():
        original = getattr(AxesDatabaseHandler, method_name, None)
        if original is None or getattr(original, "_system_delete_handler", False):
            continue

        @wraps(original)
        def allow_housekeeping(
            self, *args, __original=original, __models=allowed_models, **kwargs
        ):
            with system_delete_authority(*__models):
                return __original(self, *args, **kwargs)

        allow_housekeeping._system_delete_handler = True
        setattr(AxesDatabaseHandler, method_name, allow_housekeeping)


def _bind_admin_method(model_admin, name, wrapper_factory):
    original = getattr(model_admin, name, None)
    if original is None or getattr(original, "_superuser_admin_handler", False):
        return

    wrapper = wrapper_factory(original)
    wrapper._superuser_admin_handler = True
    setattr(model_admin, name, MethodType(wrapper, model_admin))


def _install_superuser_admin_handlers() -> None:
    # Admin modules can register Viewflow's Process and Task models after this
    # app's ready() hook. Reapply the explicit superuser-only delete policy
    # after every later registration as well as to the current registry.
    from django.contrib.admin.sites import AdminSite

    original_register = AdminSite.register
    if not getattr(original_register, "_superuser_admin_register_handler", False):
        @wraps(original_register)
        def register(self, *args, __original=original_register, **kwargs):
            result = __original(self, *args, **kwargs)
            _install_superuser_admin_handlers()
            return result

        register._superuser_admin_register_handler = True
        AdminSite.register = register

    def wrap_permission(original, *, delete=False):
        @wraps(original)
        def permission(self, request, *args, **kwargs):
            if has_superuser_authority(request.user):
                return True
            if delete:
                return False
            return original(request, *args, **kwargs)

        return permission

    def wrap_queryset(original):
        @wraps(original)
        def get_queryset(self, request):
            queryset = original(request)
            if has_superuser_authority(request.user):
                model = getattr(queryset, "model", None)
                if model is not None:
                    return model._base_manager.all()
            return queryset

        return get_queryset

    def wrap_delete_model(original):
        @wraps(original)
        def delete_model(self, request, obj):
            if has_superuser_authority(request.user):
                force_delete_objects([obj], actor=request.user)
                return None
            return original(request, obj)

        return delete_model

    def wrap_delete_queryset(original):
        @wraps(original)
        def delete_queryset(self, request, queryset):
            if has_superuser_authority(request.user):
                force_delete_objects(queryset, actor=request.user)
                return None
            return original(request, queryset)

        return delete_queryset

    for site in tuple(admin.sites.all_sites):
        site_permission = site.has_permission
        if not getattr(site_permission, "_superuser_admin_handler", False):
            @wraps(site_permission)
            def has_permission(self, request, __original=site_permission):
                if has_superuser_authority(request.user):
                    return True
                return __original(request)

            has_permission._superuser_admin_handler = True
            site.has_permission = MethodType(has_permission, site)

        for model_admin in site._registry.values():
            for permission_name in (
                "has_add_permission",
                "has_change_permission",
                "has_delete_permission",
                "has_view_permission",
                "has_module_permission",
            ):
                _bind_admin_method(
                    model_admin,
                    permission_name,
                    lambda original, delete=permission_name == "has_delete_permission":
                        wrap_permission(original, delete=delete),
                )
            _bind_admin_method(model_admin, "get_queryset", wrap_queryset)
            _bind_admin_method(model_admin, "delete_model", wrap_delete_model)
            _bind_admin_method(model_admin, "delete_queryset", wrap_delete_queryset)

            for inline_class in model_admin.inlines:
                for permission_name in (
                    "has_add_permission",
                    "has_change_permission",
                    "has_delete_permission",
                    "has_view_permission",
                ):
                    original = getattr(inline_class, permission_name, None)
                    if original is None or getattr(
                        original, "_superuser_admin_handler", False
                    ):
                        continue

                    delete = permission_name == "has_delete_permission"

                    @wraps(original)
                    def wrapped(
                        self,
                        request,
                        *args,
                        __original=original,
                        __delete=delete,
                        **kwargs,
                    ):
                        if has_superuser_authority(request.user):
                            return True
                        if __delete:
                            return False
                        return __original(self, request, *args, **kwargs)

                    wrapped._superuser_admin_handler = True
                    setattr(inline_class, permission_name, wrapped)

                original = getattr(inline_class, "get_queryset", None)
                if original is not None and not getattr(
                    original, "_superuser_admin_handler", False
                ):
                    @wraps(original)
                    def wrapped(self, request, __original=original):
                        queryset = __original(self, request)
                        if has_superuser_authority(request.user):
                            model = getattr(queryset, "model", None)
                            if model is not None:
                                return model._base_manager.all()
                        return queryset

                    wrapped._superuser_admin_handler = True
                    inline_class.get_queryset = wrapped


def _install_superuser_drf_handlers() -> None:
    try:
        from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
        from rest_framework.generics import GenericAPIView
        from rest_framework.views import APIView
    except ImportError:
        return

    original_check_permissions = APIView.check_permissions
    if not getattr(original_check_permissions, "_superuser_drf_handler", False):
        @wraps(original_check_permissions)
        def check_permissions(self, request):
            if has_superuser_authority(request.user):
                return None
            action = getattr(self, "action", None)
            action_name = str(action or "").casefold()
            if request.method.upper() == "DELETE" or any(
                marker in action_name
                for marker in ("delete", "remove", "purge", "destroy", "erase")
            ):
                raise DRFPermissionDenied(
                    "Only superusers can delete records through the API."
                )
            return original_check_permissions(self, request)

        check_permissions._superuser_drf_handler = True
        APIView.check_permissions = check_permissions

    original_check_object_permissions = APIView.check_object_permissions
    if not getattr(original_check_object_permissions, "_superuser_drf_handler", False):
        @wraps(original_check_object_permissions)
        def check_object_permissions(self, request, obj):
            if has_superuser_authority(request.user):
                return None
            return original_check_object_permissions(self, request, obj)

        check_object_permissions._superuser_drf_handler = True
        APIView.check_object_permissions = check_object_permissions

    original_filter_queryset = GenericAPIView.filter_queryset
    if not getattr(original_filter_queryset, "_superuser_drf_handler", False):
        @wraps(original_filter_queryset)
        def filter_queryset(self, queryset):
            if has_superuser_authority(getattr(self.request, "user", None)):
                model = getattr(queryset, "model", None)
                if model is not None:
                    return model._base_manager.all()
            return original_filter_queryset(self, queryset)

        filter_queryset._superuser_drf_handler = True
        GenericAPIView.filter_queryset = filter_queryset

    original_get_queryset = GenericAPIView.get_queryset
    if not getattr(original_get_queryset, "_superuser_drf_handler", False):
        @wraps(original_get_queryset)
        def get_queryset(self):
            queryset = original_get_queryset(self)
            if has_superuser_authority(getattr(self.request, "user", None)):
                model = getattr(queryset, "model", None)
                if model is not None:
                    return model._base_manager.all()
            return queryset

        get_queryset._superuser_drf_handler = True
        GenericAPIView.get_queryset = get_queryset


def _install_superuser_viewflow_handlers() -> None:
    try:
        from viewflow.workflow.base import Flow
        from viewflow.workflow.nodes.start import Start
        from viewflow.workflow.nodes.view import View
        from viewflow.workflow.status import STATUS
    except ImportError:
        return

    original_start = Start.can_execute
    if not getattr(original_start, "_superuser_viewflow_handler", False):
        @wraps(original_start)
        def can_start(self, user, task=None):
            if has_superuser_authority(user):
                if not getattr(user, "is_authenticated", False):
                    return False
                return task is None or getattr(task, "status", None) == STATUS.NEW
            return original_start(self, user, task)

        can_start._superuser_viewflow_handler = True
        Start.can_execute = can_start

    for name in ("can_execute", "can_assign", "can_unassign"):
        original = getattr(View, name)
        if getattr(original, "_superuser_viewflow_handler", False):
            continue

        @wraps(original)
        def view_permission(self, user, *args, __original=original, **kwargs):
            if has_superuser_authority(user):
                return bool(getattr(user, "is_authenticated", False))
            return __original(self, user, *args, **kwargs)

        view_permission._superuser_viewflow_handler = True
        setattr(View, name, view_permission)

    for name in ("has_view_permission", "has_manage_permission"):
        original = getattr(Flow, name)
        if getattr(original, "_superuser_viewflow_handler", False):
            continue

        @wraps(original)
        def flow_permission(self, user, *args, __original=original, **kwargs):
            if has_superuser_authority(user):
                return bool(getattr(user, "is_authenticated", False))
            return __original(self, user, *args, **kwargs)

        flow_permission._superuser_viewflow_handler = True
        setattr(Flow, name, flow_permission)


def install_superuser_authorization() -> None:
    """Install the app-wide Django, admin, API, deletion, and Viewflow hooks."""
    _install_superuser_delete_handlers()
    _install_superuser_model_delete_handlers()
    _install_superuser_queryset_delete_handlers()
    _install_axes_housekeeping_delete_authority()
    _install_superuser_admin_handlers()
    _install_superuser_drf_handlers()
    _install_superuser_viewflow_handlers()
