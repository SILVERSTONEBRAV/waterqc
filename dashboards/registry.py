from __future__ import annotations

import importlib
import json
import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.apps import apps
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connections
from django.utils import timezone

from .autodiscovery import autodiscover_modules

logger = logging.getLogger(__name__)


class RegistryKernel:
    REGISTRY_MAP = {
        "dashboards":
            "dashboards.registries.dashboard.DashboardRegistry",
        "widgets":
            "dashboards.registries.widget.WidgetRegistry",
        "charts":
            "dashboards.registries.chart.ChartRegistry",
        "kpis":
            "dashboards.registries.kpi.KPIRegistry",
        "reports":
            "dashboards.registries.report.ReportRegistry",
        "forecasts":
            "dashboards.registries.forecast.ForecastRegistry",
        "ml_models":
            "dashboards.registries.ml.MLRegistry",
        "analytics":
            "dashboards.registries.analytics.AnalyticsRegistry",
        "notifications":
            "dashboards.registries.notification.NotificationRegistry",
        "selectors":
            "dashboards.registries.selector.SelectorRegistry",
        "services":
            "dashboards.registries.service.ServiceRegistry",
    }

    def __init__(self):
        self.started_at = timezone.now()

        self._lock = threading.RLock()
        self._discovered = False

        self._registries = OrderedDict()
        self._snapshots = OrderedDict()
        self._metadata = {}

        self.executor = ThreadPoolExecutor(
            max_workers=32,
            thread_name_prefix="dashboard-kernel",
        )

    def _import_class(
        self,
        dotted_path: str,
    ):
        module_path, cls_name = (
            dotted_path.rsplit(".", 1)
        )

        module = importlib.import_module(
            module_path
        )

        return getattr(
            module,
            cls_name,
        )

    def get_registry(
        self,
        name: str,
    ):
        if name not in self.REGISTRY_MAP:
            raise KeyError(name)

        with self._lock:
            registry = self._registries.get(
                name
            )

            if registry is None:
                cls = self._import_class(
                    self.REGISTRY_MAP[name]
                )

                registry = cls()

                self._registries[
                    name
                ] = registry

            return registry

    @property
    def registries(self):
        return OrderedDict(
            (
                name,
                self.get_registry(name),
            )
            for name in self.REGISTRY_MAP
        )

    def has_registry(
        self,
        name: str,
    ):
        return (
            name in self.REGISTRY_MAP
        )

    def autodiscover(
        self,
        force: bool = False,
    ):
        with self._lock:
            if (
                self._discovered
                and not force
            ):
                return

            autodiscover_modules()

            self._discovered = True

            logger.info(
                "Dashboard registries discovered."
            )

    def reload(self):
        with self._lock:
            self.shutdown()

            self._registries.clear()
            self._discovered = False

            self.autodiscover()

    def snapshot(self):
        snapshot = self.dump()

        self._snapshots[
            timezone.now().isoformat()
        ] = snapshot

        return snapshot

    def snapshots(self):
        return self._snapshots

    def search(
        self,
        keyword: str,
    ):
        keyword = keyword.lower()

        results = {}

        for name, registry in (
            self.registries.items()
        ):
            matches = registry.search(
                keyword
            )

            if matches:
                results[name] = matches

        return results

    def validate(self):
        issues = []

        for name, registry in (
            self.registries.items()
        ):
            try:
                registry.statistics()
                registry.health()
            except Exception as exc:
                issues.append(
                    {
                        "registry":
                            name,
                        "error":
                            str(exc),
                    }
                )

        return issues

    def metrics(self):
        return {
            "uptime":
                str(
                    timezone.now()
                    - self.started_at
                ),
            "installed_apps":
                len(
                    apps.get_app_configs()
                ),
            "registries":
                {
                    name: {
                        "items":
                            len(
                                registry
                            ),
                        "statistics":
                            registry.statistics(),
                    }
                    for name, registry
                    in self.registries.items()
                },
            "database_connections":
                len(
                    connections.databases
                ),
            "channels_enabled":
                bool(
                    get_channel_layer()
                ),
            "cache_backend":
                cache.__class__.__name__,
            "snapshots":
                len(
                    self._snapshots
                ),
            "discovered":
                self._discovered,
        }

    def health(self):
        issues = self.validate()

        return {
            "healthy":
                len(issues) == 0,
            "timestamp":
                timezone.now(),
            "metrics":
                self.metrics(),
            "capabilities":
                self.capabilities,
            "issues":
                issues,
        }

    def dump(self):
        data = {
            name: registry.export()
            for name, registry
            in self.registries.items()
        }

        return json.loads(
            json.dumps(
                data,
                cls=DjangoJSONEncoder,
            )
        )

    def report(self):
        return {
            "started_at":
                self.started_at,
            "health":
                self.health(),
            "metrics":
                self.metrics(),
            "registries":
                {
                    name: registry.report()
                    if hasattr(
                        registry,
                        "report",
                    )
                    else registry.export()
                    for name, registry
                    in self.registries.items()
                },
        }

    def broadcast(
        self,
        group="dashboard_updates",
    ):
        channel_layer = (
            get_channel_layer()
        )

        if not channel_layer:
            return

        payload = {
            "type":
                "dashboard_update",
            "data":
                {
                    "timestamp":
                        timezone.now()
                        .isoformat(),
                    "metrics":
                        self.metrics(),
                    "health":
                        self.health(),
                },
        }

        async_to_sync(
            channel_layer.group_send
        )(
            group,
            payload,
        )

    @cached_property
    def capabilities(self):
        modules = (
            "numpy",
            "pandas",
            "plotly",
            "prophet",
            "statsmodels",
            "scipy",
            "sklearn",
            "transformers",
            "matplotlib",
            "seaborn",
            "redis",
            "celery",
            "graphene",
            "reportlab",
            "openpyxl",
            "channels",
            "django_plotly_dash",
            "slack_sdk",
            "twilio",
        )

        return {
            module:
                importlib.util.find_spec(
                    module
                )
                is not None
            for module in modules
        }

    def clear_cache(self):
        for registry in (
            self.registries.values()
        ):
            if hasattr(
                registry,
                "clear_cache",
            ):
                registry.clear_cache()

    def shutdown(self):
        for registry in (
            self._registries.values()
        ):
            try:
                registry.shutdown()
            except Exception:
                pass

        self.executor.shutdown(
            wait=False
        )

    def __getitem__(
        self,
        name: str,
    ):
        return self.get_registry(name)

    def __contains__(
        self,
        name: str,
    ):
        return self.has_registry(name)

    def __repr__(self):
        return (
            f"<RegistryKernel "
            f"registries="
            f"{len(self._registries)} "
            f"discovered="
            f"{self._discovered}>"
        )


registry = RegistryKernel()