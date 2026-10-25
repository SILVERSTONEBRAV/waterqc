from __future__ import annotations

import hashlib
import logging
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from typing import Any

from django.core.cache import cache
from django.http import (
    Http404,
    HttpResponse,
    JsonResponse,
)
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

from .autodiscovery import (
    discovery_export,
    discovery_health,
    discovery_metrics,
)
from .registry import registry

logger = logging.getLogger(__name__)


class DashboardView(LoginRequiredMixin, View):
    template_name = "dashboards/dashboard.html"

    dashboard_key: str | None = None

    cache_timeout = 300
    resolve_timeout = 60

    executor = ThreadPoolExecutor(
        max_workers=64,
        thread_name_prefix="dashboard-engine",
    )

    registry_map = (
        "widgets",
        "charts",
        "kpis",
        "reports",
        "forecasts",
        "analytics",
        "ml_models",
        "notifications",
        "selectors",
        "services",
    )

    ##################################################################
    # DISPATCH
    ##################################################################

    def dispatch(
        self,
        request,
        *args,
        **kwargs,
    ):
        self.started_at = time.perf_counter()

        self.request = request
        self.user = request.user

        if not self.user.is_authenticated:
            return self.handle_no_permission()

        registry.autodiscover()

        self.dashboard = self.get_dashboard()

        self.tenant = self.get_tenant()
        self.filters = self.get_filters()
        self.selector_values = (
            self.get_selector_values()
        )

        return super().dispatch(
            request,
            *args,
            **kwargs,
        )

    ##################################################################
    # HTTP
    ##################################################################

    def get(
        self,
        request,
        *args,
        **kwargs,
    ):
        context = self.get_context_data()

        return HttpResponse(
            render_to_string(
                self.get_template_name(),
                context,
                request=request,
            )
        )

    def post(
        self,
        request,
        *args,
        **kwargs,
    ):
        action = request.POST.get(
            "action"
        )

        if action == "refresh":
            self.clear_dashboard_cache()

        elif action == "reload":
            registry.reload()

        elif action == "snapshot":
            registry.snapshot()

        elif action == "metrics":
            return JsonResponse(
                registry.metrics()
            )

        elif action == "health":
            return JsonResponse(
                registry.health()
            )

        elif action == "discovery":
            return JsonResponse(
                discovery_export()
            )

        return self.get(
            request,
            *args,
            **kwargs,
        )

    ##################################################################
    # DASHBOARD LOOKUP
    ##################################################################

    def get_dashboard(self):
        dashboards = registry[
            "dashboards"
        ]

        if self.dashboard_key:
            item = dashboards.get(
                self.dashboard_key
            )

            if item:
                self._check_dashboard_access(item)
                return item.obj

            raise Http404(
                f"Dashboard "
                f"'{self.dashboard_key}' "
                f"not found."
            )

        slug = self.kwargs.get(
            "slug"
        )

        if not slug:
            raise Http404(
                "Dashboard slug missing."
            )

        for item in dashboards:
            dashboard = item.obj

            if (
                getattr(
                    dashboard,
                    "slug",
                    None,
                )
                == slug
            ):
                self._check_dashboard_access(item)
                return dashboard

        raise Http404(
            f"Dashboard '{slug}' "
            f"does not exist."
        )

    def _check_dashboard_access(self, item):
        permissions = self._permissions_for(item)
        if permissions and not (
            self.user.is_superuser
            or self.user.has_perms(list(permissions))
        ):
            # Hide dashboards the user cannot access, as Django admin does in its app list.
            raise Http404

    @staticmethod
    def _permissions_for(item):
        permissions = set()
        for source in (
            getattr(item, "permissions", ()),
            getattr(item, "metadata", {}).get("permissions", ()),
            getattr(getattr(item, "obj", None), "permissions", ()),
        ):
            if isinstance(source, str):
                permissions.add(source)
            elif source:
                permissions.update(source)
        return permissions

    ##################################################################
    # TEMPLATE
    ##################################################################

    def get_template_name(self):
        return getattr(
            self.dashboard,
            "template_name",
            self.template_name,
        )

    ##################################################################
    # CONTEXT
    ##################################################################

    def get_context_data(self):
        key = self.dashboard_cache_key()

        context = cache.get(key)

        if context:
            return context

        components = (
            self.resolve_dashboard()
        )

        context = {
            "dashboard":
                self.dashboard,

            "metadata":
                self.dashboard_metadata(),

            "components":
                components,

            "selectors":
                components.get(
                    "selectors",
                    [],
                ),

            "filters":
                self.filters,

            "selector_values":
                self.selector_values,

            "tenant":
                self.tenant,

            "metrics":
                registry.metrics(),

            "health":
                registry.health(),

            "discovery_metrics":
                discovery_metrics(),

            "discovery_health":
                discovery_health(),

            "generated_at":
                timezone.now(),

            "execution_time":
                self.execution_time(),

            "kernel_report":
                registry.report(),
        }

        cache.set(
            key,
            context,
            getattr(
                self.dashboard,
                "cache_timeout",
                self.cache_timeout,
            ),
        )

        return context

    ##################################################################
    # RESOLUTION ENGINE
    ##################################################################

    def resolve_dashboard(self):
        result = {}
        futures = {}

        for name in self.registry_map:
            keys = getattr(
                self.dashboard,
                name,
                (),
            )

            futures[
                self.executor.submit(
                    self.resolve_registry,
                    name,
                    keys,
                )
            ] = name

        for future in as_completed(
            futures,
            timeout=self.resolve_timeout,
        ):
            name = futures[
                future
            ]

            try:
                result[name] = (
                    future.result()
                )

            except Exception:
                logger.exception(
                    "Failed resolving "
                    "dashboard section %s",
                    name,
                )

                result[name] = []

        return result

    ##################################################################
    # REGISTRY RESOLUTION
    ##################################################################

    def resolve_registry(
        self,
        registry_name,
        keys,
    ):
        if not keys:
            return []

        component_registry = registry[
            registry_name
        ]

        resolved = []

        futures = {}

        with ThreadPoolExecutor(
            max_workers=32
        ) as executor:

            for key in keys:
                item = component_registry.get(key)
                permissions = self._permissions_for(item) if item else set()
                if permissions and not (
                    self.user.is_superuser
                    or self.user.has_perms(list(permissions))
                ):
                    continue
                futures[
                    executor.submit(
                        self.resolve_component,
                        component_registry,
                        registry_name,
                        key,
                    )
                ] = key

            for future in as_completed(
                futures
            ):
                key = futures[
                    future
                ]

                try:
                    component = (
                        future.result()
                    )

                    if component:
                        resolved.append(
                            component
                        )

                except Exception:
                    logger.exception(
                        "%s:%s failed",
                        registry_name,
                        key,
                    )

        return sorted(
            resolved,
            key=lambda x:
            x.get(
                "priority",
                0,
            ),
            reverse=True,
        )

    ##################################################################
    # COMPONENT RESOLUTION
    ##################################################################

    def resolve_component(
        self,
        component_registry,
        registry_name,
        key,
    ):
        cache_key = (
            f"dashboard:"
            f"{registry_name}:"
            f"{key}:"
            f"{self.tenant}"
        )

        value = cache.get(
            cache_key
        )

        if value:
            return value

        started = time.perf_counter()

        item = component_registry.get(
            key
        )

        if item is None:
            return None

        component = (
            component_registry.resolve(
                key
            )
        )

        payload = {
            "key":
                key,

            "component":
                component,

            "priority":
                getattr(
                    item,
                    "priority",
                    0,
                ),

            "metadata":
                getattr(
                    item,
                    "metadata",
                    {},
                ),

            "tags":
                list(
                    getattr(
                        item,
                        "tags",
                        set(),
                    )
                ),

            "permissions":
                list(
                    getattr(
                        item,
                        "permissions",
                        set(),
                    )
                ),

            "resolved_at":
                timezone.now(),

            "execution_time":
                round(
                    time.perf_counter()
                    - started,
                    5,
                ),
        }

        cache.set(
            cache_key,
            payload,
            self.cache_timeout,
        )

        return payload

    ##################################################################
    # FILTERS
    ##################################################################

    def get_filters(self):
        return dict(
            self.request.GET.items()
        )

    def get_selector_values(self):
        return {
            k: v
            for k, v in self.request.GET.items()
            if k.startswith(
                "selector_"
            )
        }

    ##################################################################
    # TENANCY
    ##################################################################

    def get_tenant(self):
        tenant = getattr(
            self.request,
            "tenant",
            None,
        )

        if tenant:
            return str(
                getattr(
                    tenant,
                    "pk",
                    tenant,
                )
            )

        return "default"

    ##################################################################
    # CACHE
    ##################################################################

    def dashboard_cache_key(
        self,
    ):
        payload = {
            "dashboard":
                self.dashboard.key,
            "tenant":
                self.tenant,
            "user":
                getattr(
                    self.user,
                    "pk",
                    None,
                ),
            "filters":
                self.filters,
            "selectors":
                self.selector_values,
        }

        digest = hashlib.sha256(
            str(payload).encode()
        ).hexdigest()

        return (
            f"dashboard:"
            f"context:"
            f"{digest}"
        )

    def clear_dashboard_cache(
        self,
    ):
        cache.delete(
            self.dashboard_cache_key()
        )

    ##################################################################
    # METADATA
    ##################################################################

    def dashboard_metadata(
        self,
    ):
        dashboard = self.dashboard

        return {
            "key":
                dashboard.key,
            "name":
                dashboard.name,
            "slug":
                dashboard.slug,
            "description":
                dashboard.description,
            "icon":
                dashboard.icon,
            "color":
                dashboard.color,
            "accent":
                dashboard.accent,
            "group":
                dashboard.group,
            "category":
                dashboard.category,
            "priority":
                dashboard.priority,
            "owner":
                dashboard.owner,
            "version":
                dashboard.version,
            "permissions":
                dashboard.permissions,
            "tags":
                dashboard.tags,
            "realtime":
                dashboard.realtime,
            "mobile_enabled":
                dashboard.mobile_enabled,
            "tenant_aware":
                dashboard.tenant_aware,
            "audit_enabled":
                dashboard.audit_enabled,
            "refresh_interval":
                dashboard.refresh_interval,
            "cache_timeout":
                dashboard.cache_timeout,
            "websocket_group":
                dashboard.websocket_group,
            "websocket_endpoint":
                dashboard.websocket_endpoint,
            "export_formats":
                dashboard.export_formats,
        }

    ##################################################################
    # PERFORMANCE
    ##################################################################

    def execution_time(
        self,
    ):
        return round(
            time.perf_counter()
            - self.started_at,
            5,
        )

    ##################################################################
    # REALTIME
    ##################################################################

    def websocket_context(
        self,
    ):
        return {
            "group":
                self.dashboard.websocket_group,
            "endpoint":
                self.dashboard.websocket_endpoint,
            "realtime":
                self.dashboard.realtime,
            "refresh_interval":
                self.dashboard.refresh_interval,
        }
