from __future__ import annotations

import hashlib
import inspect
import json
import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from django.core.cache import cache
from django.utils import timezone
from django.utils.functional import cached_property

from .base import BaseRegistry, RegistryItem


class KPIRegistry(BaseRegistry):
    category = "kpis"

    def __init__(self):
        super().__init__()

        self._groups: dict[str, dict[str, RegistryItem]] = defaultdict(dict)
        self._targets: dict[str, dict[str, RegistryItem]] = defaultdict(dict)
        self._units: dict[str, dict[str, RegistryItem]] = defaultdict(dict)

        self._scorecards: dict[str, Callable] = {}
        self._calculators: dict[str, Callable] = {}
        self._aggregations: dict[str, Callable] = {}
        self._subscriptions: dict[str, set[str]] = defaultdict(set)

        self._lock = threading.RLock()
        self.executor = ThreadPoolExecutor(
            max_workers=16,
            thread_name_prefix="kpis",
        )

    ####################################################################
    # REGISTRATION
    ####################################################################

    def register(
        self,
        key: str,
        obj: Any,
        *,
        group: str = "general",
        unit: str = "",
        aggregation: str = "sum",
        target: Any = None,
        threshold: Any = None,
        benchmark: Any = None,
        realtime: bool = False,
        dashboard: bool = False,
        cache_timeout: int = 300,
        singleton: bool = False,
        lazy: bool = False,
        tags=None,
        permissions=None,
        dependencies=None,
        version: str = "1.0.0",
        **metadata,
    ) -> RegistryItem:
        metadata.update(
            {
                "group": group,
                "unit": unit,
                "aggregation": aggregation,
                "target": target,
                "threshold": threshold,
                "benchmark": benchmark,
                "realtime": realtime,
                "dashboard": dashboard,
                "cache": True,
                "cache_timeout": cache_timeout,
            }
        )

        item = super().register(
            key,
            obj,
            singleton=singleton,
            lazy=lazy,
            tags=tags or [],
            permissions=permissions or [],
            dependencies=dependencies or [],
            version=version,
            **metadata,
        )

        self._groups[group][key] = item

        if unit:
            self._units[unit][key] = item

        if target is not None:
            self._targets[str(target)][key] = item

        return item

    ####################################################################
    # EXTENSIONS
    ####################################################################

    def register_calculator(
        self,
        name: str,
        fn: Callable,
    ):
        self._calculators[name] = fn

    def register_scorecard(
        self,
        name: str,
        fn: Callable,
    ):
        self._scorecards[name] = fn

    def register_aggregation(
        self,
        name: str,
        fn: Callable,
    ):
        self._aggregations[name] = fn

    ####################################################################
    # CACHE
    ####################################################################

    def cache_key(
        self,
        key: str,
        *args,
        **kwargs,
    ) -> str:
        payload = json.dumps(
            {
                "key": key,
                "args": repr(args),
                "kwargs": repr(kwargs),
            },
            sort_keys=True,
            default=str,
        )

        digest = hashlib.sha256(
            payload.encode()
        ).hexdigest()

        return f"kpi:{digest}"

    ####################################################################
    # EXECUTION
    ####################################################################

    def compute(
        self,
        key: str,
        *args,
        refresh: bool = False,
        **kwargs,
    ):
        item = self.get(key)

        if not item:
            raise KeyError(key)

        cache_key = self.cache_key(
            key,
            *args,
            **kwargs,
        )

        if not refresh:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        obj = self.resolve(key)

        if inspect.isclass(obj):
            obj = obj()

        if callable(obj):
            try:
                sig = inspect.signature(obj)

                if "context" in sig.parameters:
                    value = obj(
                        context=kwargs.get(
                            "context"
                        ),
                        *args,
                        **kwargs,
                    )
                else:
                    value = obj(
                        *args,
                        **kwargs,
                    )
            except Exception:
                value = obj(
                    *args,
                    **kwargs,
                )
        else:
            value = obj

        cache.set(
            cache_key,
            value,
            item.metadata.get(
                "cache_timeout",
                300,
            ),
        )

        item.touch()

        return value

    def compute_many(
        self,
        keys: list[str],
        *args,
        **kwargs,
    ):
        return {
            key: self.compute(
                key,
                *args,
                **kwargs,
            )
            for key in keys
        }

    ####################################################################
    # ASYNC
    ####################################################################

    def submit(
        self,
        key: str,
        *args,
        **kwargs,
    ) -> Future:
        return self.executor.submit(
            self.compute,
            key,
            *args,
            **kwargs,
        )

    def compute_parallel(
        self,
        keys: list[str],
        *args,
        **kwargs,
    ):
        futures = {
            key: self.submit(
                key,
                *args,
                **kwargs,
            )
            for key in keys
        }

        return {
            key: future.result()
            for key, future in futures.items()
        }

    ####################################################################
    # SCORECARDS
    ####################################################################

    def scorecard(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._scorecards.get(name)

        if not fn:
            raise KeyError(name)

        return fn(*args, **kwargs)

    def calculate(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._calculators.get(name)

        if not fn:
            raise KeyError(name)

        return fn(*args, **kwargs)

    def aggregate(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._aggregations.get(name)

        if not fn:
            raise KeyError(name)

        return fn(*args, **kwargs)

    ####################################################################
    # FILTERS
    ####################################################################

    def by_group(
        self,
        group: str,
    ):
        return self._groups.get(
            group,
            {},
        )

    def by_target(
        self,
        target: str,
    ):
        return self._targets.get(
            str(target),
            {},
        )

    def by_unit(
        self,
        unit: str,
    ):
        return self._units.get(
            unit,
            {},
        )

    def groups(self):
        return dict(self._groups)

    def realtime(self):
        return {
            k: v
            for k, v in self._items.items()
            if v.metadata.get(
                "realtime"
            )
        }

    def dashboards(self):
        return {
            k: v
            for k, v in self._items.items()
            if v.metadata.get(
                "dashboard"
            )
        }

    def trending(self):
        return {
            k: v
            for k, v in self._items.items()
            if (
                v.metadata.get(
                    "realtime"
                )
                or v.metadata.get(
                    "threshold"
                )
                is not None
            )
        }

    def critical(self):
        return {
            k: v
            for k, v in self._items.items()
            if v.metadata.get(
                "threshold"
            )
            is not None
        }

    ####################################################################
    # SUBSCRIPTIONS
    ####################################################################

    def subscribe(
        self,
        key: str,
        channel: str,
    ):
        self._subscriptions[key].add(
            channel
        )

    def unsubscribe(
        self,
        key: str,
        channel: str,
    ):
        self._subscriptions[key].discard(
            channel
        )

    ####################################################################
    # ANALYTICS
    ####################################################################

    def attainment(
        self,
        key: str,
        value: float,
    ) -> float | None:
        item = self.get(key)

        if not item:
            return None

        target = item.metadata.get(
            "target"
        )

        if target in (
            None,
            0,
        ):
            return None

        return (
            value / float(target)
        ) * 100.0

    def variance(
        self,
        key: str,
        value: float,
    ) -> float | None:
        item = self.get(key)

        if not item:
            return None

        target = item.metadata.get(
            "target"
        )

        if target is None:
            return None

        return value - float(target)

    ####################################################################
    # CAPABILITIES
    ####################################################################

    @cached_property
    def capabilities(self):
        return {
            "scorecards": True,
            "targets": True,
            "benchmarking": True,
            "aggregation": True,
            "realtime": True,
            "forecast_kpis": True,
            "spc": True,
            "trend_analysis": True,
            "executive_dashboards": True,
            "grouping": True,
            "caching": True,
            "async_execution": True,
            "parallel_execution": True,
            "subscriptions": True,
        }

    ####################################################################
    # STATISTICS
    ####################################################################

    def statistics(self):
        return {
            "kpis": len(self),
            "groups": {
                k: len(v)
                for k, v in self._groups.items()
            },
            "targets": {
                k: len(v)
                for k, v in self._targets.items()
            },
            "units": {
                k: len(v)
                for k, v in self._units.items()
            },
            "calculators": len(
                self._calculators
            ),
            "scorecards": len(
                self._scorecards
            ),
            "aggregations": len(
                self._aggregations
            ),
            "realtime": len(
                self.realtime()
            ),
            "critical": len(
                self.critical()
            ),
            "dashboard": len(
                self.dashboards()
            ),
            "subscriptions": {
                k: len(v)
                for k, v in self._subscriptions.items()
            },
            "capabilities": self.capabilities,
            "timestamp": timezone.now(),
        }

    ####################################################################
    # EXPORT
    ####################################################################

    def schema(self):
        return {
            k: {
                "group": v.metadata.get(
                    "group"
                ),
                "unit": v.metadata.get(
                    "unit"
                ),
                "aggregation": v.metadata.get(
                    "aggregation"
                ),
                "target": v.metadata.get(
                    "target"
                ),
                "threshold": v.metadata.get(
                    "threshold"
                ),
                "benchmark": v.metadata.get(
                    "benchmark"
                ),
                "realtime": v.metadata.get(
                    "realtime"
                ),
                "dashboard": v.metadata.get(
                    "dashboard"
                ),
                "tags": list(v.tags),
                "permissions": list(
                    v.permissions
                ),
                "dependencies": list(
                    v.dependencies
                ),
                "version": v.version,
            }
            for k, v in self._items.items()
        }

    def export(self):
        return self.schema()


kpis = KPIRegistry()