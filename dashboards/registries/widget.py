from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from time import perf_counter
from typing import Any, Callable

from django.core.cache import cache
from django.utils import timezone
from django.utils.functional import cached_property

from .base import BaseRegistry

logger = logging.getLogger(__name__)


class WidgetRegistry(BaseRegistry):
    category = "widgets"

    def __init__(self):
        super().__init__()

        self._types = defaultdict(set)
        self._groups = defaultdict(set)
        self._dashboards = defaultdict(set)

        self._layouts = {}
        self._renderers = {}
        self._pipelines = {}

        self._executions = defaultdict(list)
        self._metrics = defaultdict(dict)

    def register(
        self,
        key: str,
        obj: Any,
        *,
        widget_type: str = "card",
        group: str = "general",
        dashboard: str = "default",
        width: int = 4,
        height: int = 1,
        refresh_interval: int = 300,
        realtime: bool = False,
        configurable: bool = True,
        cache_timeout: int = 300,
        singleton: bool = False,
        lazy: bool = False,
        dependencies=(),
        permissions=None,
        tags=None,
        aliases=(),
        enabled: bool = True,
        priority: int = 0,
        version: str = "1.0.0",
        **metadata,
    ):
        metadata.update(
            {
                "widget_type": widget_type,
                "group": group,
                "dashboard": dashboard,
                "width": width,
                "height": height,
                "refresh_interval": refresh_interval,
                "realtime": realtime,
                "configurable": configurable,
                "cache_timeout": cache_timeout,
            }
        )

        item = super().register(
            key=key,
            obj=obj,
            aliases=aliases,
            tags=tags or [],
            permissions=permissions or [],
            dependencies=dependencies,
            singleton=singleton,
            lazy=lazy,
            enabled=enabled,
            priority=priority,
            version=version,
            **metadata,
        )

        self._types[widget_type].add(key)
        self._groups[group].add(key)
        self._dashboards[dashboard].add(key)

        return item

    def register_layout(
        self,
        name: str,
        layout: Callable,
    ):
        self._layouts[name] = layout

    def get_layout(
        self,
        name: str,
    ):
        return self._layouts.get(name)

    def register_renderer(
        self,
        name: str,
        renderer: Callable,
    ):
        self._renderers[name] = renderer

    def register_pipeline(
        self,
        name: str,
        fn: Callable,
    ):
        self._pipelines[name] = fn

    def run_pipeline(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._pipelines.get(name)

        if fn is None:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    def cache_key(
        self,
        key: str,
        *args,
        **kwargs,
    ):
        payload = (
            f"{key}:{args}:{kwargs}"
        )

        return super().cache_key(payload)

    def generate(
        self,
        key: str,
        *args,
        refresh: bool = False,
        **kwargs,
    ):
        item = self.get(key)

        if item is None:
            raise KeyError(key)

        cache_key = self.cache_key(
            key,
            *args,
            **kwargs,
        )

        if not refresh:
            cached = cache.get(cache_key)
            if cached is not None:
                self._metrics[key] = {
                    "cached": True,
                    "executed_at": timezone.now(),
                }
                return cached

        widget = item.obj

        if inspect.isclass(widget):
            widget = widget()

        started = perf_counter()

        if callable(widget):
            result = widget(
                *args,
                **kwargs,
            )
        else:
            result = widget

        duration = (
            perf_counter() - started
        )

        self._executions[key].append(
            timezone.now()
        )

        self._metrics[key] = {
            "duration": duration,
            "cached": False,
            "executed_at": timezone.now(),
        }

        cache.set(
            cache_key,
            result,
            item.metadata.get(
                "cache_timeout",
                300,
            ),
        )

        return result

    async def agenerate(
        self,
        key: str,
        *args,
        **kwargs,
    ):
        item = self.get(key)

        if item is None:
            raise KeyError(key)

        widget = item.obj

        if inspect.isclass(widget):
            widget = widget()

        if inspect.iscoroutinefunction(
            widget
        ):
            return await widget(
                *args,
                **kwargs,
            )

        loop = asyncio.get_running_loop()

        return await loop.run_in_executor(
            self.executor,
            lambda: (
                widget(
                    *args,
                    **kwargs,
                )
                if callable(widget)
                else widget
            ),
        )

    def generate_async(
        self,
        key: str,
        *args,
        **kwargs,
    ):
        return self.executor.submit(
            self.generate,
            key,
            *args,
            **kwargs,
        )

    def generate_parallel(
        self,
        keys: list[str],
    ):
        futures = {
            k: self.generate_async(k)
            for k in keys
        }

        return {
            k: f.result()
            for k, f in futures.items()
        }

    def compose(
        self,
        *widgets,
    ):
        return [
            self.generate(widget)
            for widget in widgets
        ]

    def render(
        self,
        key: str,
        *args,
        renderer: str | None = None,
        **kwargs,
    ):
        widget = self.generate(
            key,
            *args,
            **kwargs,
        )

        if renderer:
            fn = self._renderers.get(renderer)

            if fn:
                return fn(widget)

        return widget

    def invalidate(
        self,
        key: str,
    ):
        self.invalidate_cache(
            self.cache_key(key)
        )

    def flush(self):
        for key in self.keys():
            self.invalidate(key)

    def history(
        self,
        key: str | None = None,
    ):
        if key is None:
            return dict(
                self._executions
            )

        return self._executions.get(
            key,
            [],
        )

    def by_type(
        self,
        widget_type: str,
    ):
        return [
            self.get(k)
            for k in self._types.get(
                widget_type,
                set(),
            )
        ]

    def by_group(
        self,
        group: str,
    ):
        return [
            self.get(k)
            for k in self._groups.get(
                group,
                set(),
            )
        ]

    def by_dashboard(
        self,
        dashboard: str,
    ):
        return [
            self.get(k)
            for k in self._dashboards.get(
                dashboard,
                set(),
            )
        ]

    @cached_property
    def capabilities(self):
        return {
            "plotly": True,
            "dash": True,
            "realtime": True,
            "caching": True,
            "async": True,
            "pipelines": True,
            "layouts": True,
            "drag_drop": True,
            "configuration": True,
            "notifications": True,
            "forecasting": True,
            "machine_learning": True,
            "maps": True,
            "graphql": True,
            "reporting": True,
            "parallel_execution": True,
            "middleware": True,
            "snapshots": True,
        }

    def statistics(self):
        return {
            "widgets": len(self),
            "types": {
                k: len(v)
                for k, v in self._types.items()
            },
            "groups": {
                k: len(v)
                for k, v in self._groups.items()
            },
            "dashboards": {
                k: len(v)
                for k, v in self._dashboards.items()
            },
            "layouts": len(
                self._layouts
            ),
            "renderers": len(
                self._renderers
            ),
            "pipelines": len(
                self._pipelines
            ),
            "executions": sum(
                len(v)
                for v in self._executions.values()
            ),
            "capabilities":
                self.capabilities,
        }

    def schema(self):
        return {
            k: {
                "widget_type":
                    v.metadata.get(
                        "widget_type"
                    ),
                "group":
                    v.metadata.get(
                        "group"
                    ),
                "dashboard":
                    v.metadata.get(
                        "dashboard"
                    ),
                "width":
                    v.metadata.get(
                        "width"
                    ),
                "height":
                    v.metadata.get(
                        "height"
                    ),
                "refresh_interval":
                    v.metadata.get(
                        "refresh_interval"
                    ),
                "realtime":
                    v.metadata.get(
                        "realtime"
                    ),
                "configurable":
                    v.metadata.get(
                        "configurable"
                    ),
                "priority":
                    v.priority,
                "version":
                    v.version,
                "enabled":
                    v.enabled,
                "tags":
                    list(v.tags),
                "permissions":
                    list(v.permissions),
                "dependencies":
                    list(v.dependencies),
            }
            for k, v in self._items.items()
        }

    def health(self):
        return {
            "healthy": True,
            "category": self.category,
            "metrics": self.statistics(),
        }

    def report(self):
        return {
            "category": self.category,
            "health": self.health(),
            "statistics": self.statistics(),
            "schema": self.schema(),
        }


widgets = WidgetRegistry()