# dashboards/autodiscovery.py

from __future__ import annotations

import hashlib
import importlib
import logging
import pkgutil
import threading
import time

from collections import defaultdict
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.dispatch import Signal
from django.utils import timezone

logger = logging.getLogger(__name__)

discovery_started = Signal()
discovery_finished = Signal()
module_discovered = Signal()
module_failed = Signal()


DEFAULT_MODULES = (
    "dashboards.dashboards",
    "dashboards.widgets",
    "dashboards.charts",
    "dashboards.kpis",
    "dashboards.reports",
    "dashboards.forecasts",
    "dashboards.ml",
    "dashboards.analytics",
    "dashboards.notifications",
    "dashboards.selectors",
)


@dataclass(slots=True)
class DiscoveryRecord:
    app_label: str
    module: str
    loaded: bool = False
    failed: bool = False
    duration: float = 0.0
    imported_at: Any = None
    error: str | None = None
    checksum: str | None = None
    dependencies: list[str] = field(
        default_factory=list
    )


class DiscoveryRegistry:
    def __init__(self):
        self._lock = threading.RLock()

        self.loaded = defaultdict(set)
        self.failed = defaultdict(dict)
        self.records = {}
        self.manifest = set()

        self.started_at = None
        self.finished_at = None

    def clear(self):
        with self._lock:
            self.loaded.clear()
            self.failed.clear()
            self.records.clear()
            self.manifest.clear()

    def add(
        self,
        record: DiscoveryRecord,
    ):
        with self._lock:
            key = (
                record.app_label,
                record.module,
            )

            self.records[key] = record

            if record.loaded:
                self.loaded[
                    record.app_label
                ].add(record.module)
                self.manifest.add(
                    record.module
                )

            if record.failed:
                self.failed[
                    record.app_label
                ][record.module] = (
                    record.error
                )

    def metrics(self):
        return {
            "apps": len(
                apps.get_app_configs()
            ),
            "loaded_apps": len(
                self.loaded
            ),
            "loaded_modules": sum(
                len(v)
                for v in self.loaded.values()
            ),
            "failed_modules": sum(
                len(v)
                for v in self.failed.values()
            ),
            "manifest_size": len(
                self.manifest
            ),
            "records": len(
                self.records
            ),
            "started_at":
                self.started_at,
            "finished_at":
                self.finished_at,
        }

    def export(self):
        return {
            "loaded": {
                k: sorted(v)
                for k, v in self.loaded.items()
            },
            "failed": self.failed,
            "metrics": self.metrics(),
        }


discovery_state = DiscoveryRegistry()


def get_discovery_modules():
    return tuple(
        getattr(
            settings,
            "DASHBOARD_PACKAGE_MODULES",
            DEFAULT_MODULES,
        )
    )


def get_plugin_packages():
    return tuple(
        getattr(
            settings,
            "DASHBOARD_PLUGIN_PACKAGES",
            (),
        )
    )


def module_checksum(
    dotted_path: str,
):
    try:
        spec = importlib.util.find_spec(
            dotted_path
        )

        if not spec:
            return None

        if not spec.origin:
            return None

        path = Path(spec.origin)

        if not path.exists():
            return None

        return hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

    except Exception:
        return None


def import_module(
    app_label: str,
    dotted_path: str,
):
    started = time.perf_counter()

    record = DiscoveryRecord(
        app_label=app_label,
        module=dotted_path,
    )

    try:
        importlib.import_module(
            dotted_path
        )

        record.loaded = True
        record.imported_at = (
            timezone.now()
        )
        record.checksum = (
            module_checksum(
                dotted_path
            )
        )

        module_discovered.send(
            sender=None,
            record=record,
        )

    except ModuleNotFoundError as exc:
        if exc.name != dotted_path:
            record.failed = True
            record.error = str(exc)

            module_failed.send(
                sender=None,
                record=record,
            )

            logger.exception(
                "Dashboard import failure %s",
                dotted_path,
            )

    except Exception as exc:
        record.failed = True
        record.error = str(exc)

        module_failed.send(
            sender=None,
            record=record,
        )

        logger.exception(
            "Dashboard import failure %s",
            dotted_path,
        )

    finally:
        record.duration = (
            time.perf_counter()
            - started
        )

        discovery_state.add(
            record
        )

    return record


def discover_app(app_config):
    modules = []

    for module in (
        get_discovery_modules()
    ):
        dotted = (
            f"{app_config.name}.{module}"
        )

        record = import_module(
            app_config.label,
            dotted,
        )

        if record.loaded:
            modules.append(dotted)

    return modules


@lru_cache(maxsize=1)
def autodiscover_modules():
    discovery_state.started_at = (
        timezone.now()
    )

    discovery_started.send(
        sender=None
    )

    discovered = []

    app_configs = list(
        apps.get_app_configs()
    )

    workers = min(
        32,
        max(
            4,
            len(app_configs),
        ),
    )

    with ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="dashboard-discovery",
    ) as executor:

        futures = [
            executor.submit(
                discover_app,
                app,
            )
            for app in app_configs
        ]

        for future in as_completed(
            futures
        ):
            try:
                discovered.extend(
                    future.result()
                )
            except Exception:
                logger.exception(
                    "Dashboard discovery task failed."
                )

    load_plugin_packages()

    discovery_state.finished_at = (
        timezone.now()
    )

    discovery_finished.send(
        sender=None,
        discovered=tuple(
            discovered
        ),
    )

    cache.set(
        "dashboard_discovery_manifest",
        tuple(discovered),
        None,
    )

    return tuple(
        sorted(
            set(discovered)
        )
    )


def load_plugin_packages():
    for package in (
        get_plugin_packages()
    ):
        try:
            pkg = importlib.import_module(
                package
            )

            if not hasattr(
                pkg,
                "__path__",
            ):
                continue

            for module in pkgutil.iter_modules(
                pkg.__path__,
                pkg.__name__ + ".",
            ):
                try:
                    importlib.import_module(
                        module.name
                    )

                    discovery_state.manifest.add(
                        module.name
                    )

                except Exception:
                    logger.exception(
                        "Failed loading plugin %s",
                        module.name,
                    )

        except Exception:
            logger.exception(
                "Failed loading plugin package %s",
                package,
            )


def rediscover():
    discovery_state.clear()

    autodiscover_modules.cache_clear()

    cache.delete(
        "dashboard_discovery_manifest"
    )

    return autodiscover_modules()


def module_exists(
    app_label: str,
    module: str,
):
    return (
        f"{apps.get_app_config(app_label).name}.{module}"
        in discovery_state.manifest
    )


def imported_modules():
    return sorted(
        discovery_state.manifest
    )


def discovery_metrics():
    return (
        discovery_state.metrics()
    )


def discovery_health():
    metrics = discovery_metrics()

    return {
        "healthy":
            metrics["failed_modules"]
            == 0,
        "timestamp":
            timezone.now(),
        "metrics":
            metrics,
    }


def discovery_export():
    return (
        discovery_state.export()
    )