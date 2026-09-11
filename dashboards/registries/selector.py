from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from time import perf_counter
from typing import Any, Callable

from django.core.cache import cache
from django.db.models import QuerySet
from django.utils.functional import cached_property

from .base import BaseRegistry


class SelectorRegistry(BaseRegistry):
    category = "selectors"

    def __init__(self):
        super().__init__(max_workers=16)

        self._apps = defaultdict(set)
        self._domains = defaultdict(set)
        self._pipelines = {}
        self._executors = {}
        self._analytics = defaultdict(dict)

    def register(
        self,
        key: str,
        obj: Any,
        *,
        app_label: str = "default",
        domain: str = "general",
        cacheable: bool = True,
        cache_timeout: int = 300,
        async_enabled: bool = False,
        graphql: bool = False,
        batchable: bool = False,
        singleton: bool = False,
        dependencies=(),
        permissions=(),
        tags=(),
        **metadata,
    ):
        metadata.update(
            {
                "app_label": app_label,
                "domain": domain,
                "cache": cacheable,
                "cache_timeout": cache_timeout,
                "async_enabled": async_enabled,
                "graphql": graphql,
                "batchable": batchable,
            }
        )

        item = super().register(
            key=key,
            obj=obj,
            singleton=singleton,
            dependencies=dependencies,
            permissions=permissions,
            tags=tags,
            **metadata,
        )

        self._apps[app_label].add(key)
        self._domains[domain].add(key)

        return item

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
        pipeline = self._pipelines.get(name)

        if pipeline is None:
            raise KeyError(name)

        return pipeline(
            *args,
            **kwargs,
        )

    def register_executor(
        self,
        name: str,
        fn: Callable,
    ):
        self._executors[name] = fn

    def cache_key(
        self,
        key,
        *args,
        **kwargs,
    ):
        return (
            f"selector:{key}:"
            f"{hash(str(args)+str(kwargs))}"
        )

    def execute(
        self,
        key,
        *args,
        refresh=False,
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

        if (
            item.metadata.get("cache")
            and not refresh
        ):
            cached = cache.get(cache_key)

            if cached is not None:
                return cached

        selector = self.resolve(key)

        started = perf_counter()

        result = selector(
            *args,
            **kwargs,
        )

        duration = (
            perf_counter() - started
        )

        self._analytics[key] = {
            "duration": duration,
            "cached": False,
        }

        if item.metadata.get("cache"):
            cache.set(
                cache_key,
                result,
                timeout=item.metadata.get(
                    "cache_timeout",
                    300,
                ),
            )

        return result

    async def aexecute(
        self,
        key,
        *args,
        **kwargs,
    ):
        selector = self.resolve(key)

        if inspect.iscoroutinefunction(
            selector
        ):
            return await selector(
                *args,
                **kwargs,
            )

        loop = asyncio.get_running_loop()

        return await loop.run_in_executor(
            self.executor,
            lambda: selector(
                *args,
                **kwargs,
            ),
        )

    def batch(
        self,
        key,
        items,
        **kwargs,
    ):
        selector = self.resolve(key)

        return [
            selector(
                item,
                **kwargs,
            )
            for item in items
        ]

    def batch_parallel(
        self,
        key,
        items,
        **kwargs,
    ):
        selector = self.resolve(key)

        futures = [
            self.executor.submit(
                selector,
                item,
                **kwargs,
            )
            for item in items
        ]

        return [
            future.result()
            for future in futures
        ]

    def optimize(
        self,
        queryset: QuerySet,
        *,
        select_related=None,
        prefetch_related=None,
        only=None,
        defer=None,
    ):
        if select_related:
            queryset = queryset.select_related(
                *select_related
            )

        if prefetch_related:
            queryset = queryset.prefetch_related(
                *prefetch_related
            )

        if only:
            queryset = queryset.only(
                *only
            )

        if defer:
            queryset = queryset.defer(
                *defer
            )

        return queryset

    def paginate(
        self,
        queryset,
        *,
        offset=0,
        limit=100,
    ):
        return queryset[
            offset : offset + limit
        ]

    def stream(
        self,
        queryset,
        *,
        chunk_size=1000,
    ):
        return queryset.iterator(
            chunk_size=chunk_size
        )

    def by_app(
        self,
        app_label: str,
    ):
        return [
            self.get(k)
            for k in self._apps.get(
                app_label,
                set(),
            )
        ]

    def by_domain(
        self,
        domain: str,
    ):
        return [
            self.get(k)
            for k in self._domains.get(
                domain,
                set(),
            )
        ]

    def analytics(
        self,
        key=None,
    ):
        if key:
            return self._analytics.get(
                key,
                {}
            )

        return dict(self._analytics)

    @cached_property
    def capabilities(self):
        return {
            "caching": True,
            "batching": True,
            "parallel_batching": True,
            "async": True,
            "graphql": True,
            "query_optimization": True,
            "pagination": True,
            "streaming": True,
            "pipelines": True,
            "thread_pool": True,
            "analytics": True,
            "background_tasks": True,
            "redis": True,
        }

    def statistics(self):
        return {
            "selectors": len(self),
            "apps": len(self._apps),
            "domains": len(self._domains),
            "pipelines": len(
                self._pipelines
            ),
            "executors": len(
                self._executors
            ),
            "analytics": len(
                self._analytics
            ),
            "capabilities": (
                self.capabilities
            ),
        }

    def schema(self):
        return {
            k: {
                "app_label": v.metadata.get(
                    "app_label"
                ),
                "domain": v.metadata.get(
                    "domain"
                ),
                "tags": list(v.tags),
                "permissions": list(
                    v.permissions
                ),
                "singleton": v.singleton,
                "dependencies": list(
                    v.dependencies
                ),
                "async": v.metadata.get(
                    "async_enabled"
                ),
                "graphql": v.metadata.get(
                    "graphql"
                ),
                "batchable": v.metadata.get(
                    "batchable"
                ),
            }
            for k, v in self.items()
        }


selectors = SelectorRegistry()