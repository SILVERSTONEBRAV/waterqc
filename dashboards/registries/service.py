from __future__ import annotations

import inspect
import traceback
from collections import defaultdict
from concurrent.futures import as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .base import BaseRegistry, RegistryItem


# ============================================================
# CONTEXT
# ============================================================

@dataclass(slots=True)
class ServiceContext:
    user: Any | None = None
    request: Any | None = None
    params: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)


# ============================================================
# RESULT
# ============================================================

@dataclass(slots=True)
class ServiceResult:
    service: str
    result: Any = None
    success: bool = True
    message: str | None = None

    started_at: datetime = field(
        default_factory=timezone.now
    )
    completed_at: datetime | None = None
    duration: float = 0.0

    metadata: dict = field(default_factory=dict)

    exception: str | None = None
    traceback: str | None = None


# ============================================================
# REGISTRY
# ============================================================

class ServiceRegistry(BaseRegistry):
    category = "services"

    def __init__(self):
        super().__init__(
            max_workers=32
        )

        self._groups = defaultdict(set)
        self._pipelines = {}
        self._scheduled = {}
        self._results = []

    # =========================================================
    # REGISTRATION
    # =========================================================

    def register(
        self,
        key: str,
        obj: Any,
        *,
        group: str | None = None,
        dependencies: Iterable[str] = (),
        singleton: bool = False,
        transactional: bool = False,
        cacheable: bool = False,
        cache_timeout: int = 300,
        retry: int = 0,
        pipeline: Iterable[str] = (),
        scheduled: bool = False,
        permissions: Iterable[str] = (),
        tags: Iterable[str] = (),
        **metadata,
    ):
        metadata.update(
            {
                "group": group,
                "transactional": transactional,
                "cacheable": cacheable,
                "cache_timeout": cache_timeout,
                "retry": retry,
                "pipeline": list(pipeline),
                "scheduled": scheduled,
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

        if group:
            self._groups[group].add(key)

        if pipeline:
            self._pipelines[key] = list(
                pipeline
            )

        if scheduled:
            self._scheduled[key] = True

        return item

    # =========================================================
    # HOOKS
    # =========================================================

    def before(
        self,
        key: str,
        callback: Callable,
    ):
        self.on(
            f"before:{key}",
            callback,
        )

    def after(
        self,
        key: str,
        callback: Callable,
    ):
        self.on(
            f"after:{key}",
            callback,
        )

    def on_error(
        self,
        key: str,
        callback: Callable,
    ):
        self.on(
            f"error:{key}",
            callback,
        )

    # =========================================================
    # CACHE
    # =========================================================

    def cache_key(
        self,
        key,
        args,
        kwargs,
    ):
        return (
            f"service:"
            f"{hash((key, str(args), str(kwargs)))}"
        )

    # =========================================================
    # EXECUTION
    # =========================================================

    def _execute(
        self,
        item: RegistryItem,
        context: ServiceContext,
        *args,
        **kwargs,
    ):
        service = item.obj

        if inspect.isclass(service):
            service = service()

        if callable(service):
            sig = inspect.signature(
                service
            )

            if (
                "context"
                in sig.parameters
            ):
                return service(
                    context=context,
                    *args,
                    **kwargs,
                )

            return service(
                *args,
                **kwargs,
            )

        return service

    # =========================================================
    # RUN
    # =========================================================

    def run(
        self,
        key: str,
        *args,
        context: ServiceContext | None = None,
        refresh: bool = False,
        **kwargs,
    ):
        item = self.get(key)

        if not item:
            raise KeyError(key)

        context = (
            context
            or ServiceContext()
        )

        cache_key = self.cache_key(
            key,
            args,
            kwargs,
        )

        if (
            item.metadata.get(
                "cacheable"
            )
            and not refresh
        ):
            cached = cache.get(
                cache_key
            )
            if cached is not None:
                return cached

        started = timezone.now()

        result = ServiceResult(
            service=key,
            started_at=started,
        )

        self.emit(
            f"before:{key}",
            context,
        )

        retries = item.metadata.get(
            "retry",
            0,
        )

        attempt = 0

        while True:
            try:
                if item.metadata.get(
                    "transactional"
                ):
                    with transaction.atomic():
                        value = self._execute(
                            item,
                            context,
                            *args,
                            **kwargs,
                        )
                else:
                    value = self._execute(
                        item,
                        context,
                        *args,
                        **kwargs,
                    )

                finished = timezone.now()

                result.result = value
                result.completed_at = (
                    finished
                )
                result.duration = (
                    finished - started
                ).total_seconds()

                self._results.append(
                    result
                )

                if item.metadata.get(
                    "cacheable"
                ):
                    cache.set(
                        cache_key,
                        result,
                        timeout=item.metadata.get(
                            "cache_timeout",
                            300,
                        ),
                    )

                self.emit(
                    f"after:{key}",
                    result,
                )

                return result

            except Exception as exc:
                attempt += 1

                if attempt <= retries:
                    continue

                finished = timezone.now()

                result.success = False
                result.completed_at = (
                    finished
                )
                result.duration = (
                    finished - started
                ).total_seconds()

                result.exception = str(exc)
                result.traceback = (
                    traceback.format_exc()
                )

                self._results.append(
                    result
                )

                self.emit(
                    f"error:{key}",
                    result,
                )

                raise

    # =========================================================
    # ASYNC
    # =========================================================

    def run_async(
        self,
        key: str,
        *args,
        **kwargs,
    ):
        return self.executor.submit(
            self.run,
            key,
            *args,
            **kwargs,
        )

    # =========================================================
    # PARALLEL
    # =========================================================

    def run_parallel(
        self,
        keys: list[str],
        *,
        context=None,
    ):
        futures = {
            key: self.run_async(
                key,
                context=context,
            )
            for key in keys
        }

        results = {}

        for future in as_completed(
            futures.values()
        ):
            for key, f in futures.items():
                if f == future:
                    results[key] = (
                        future.result()
                    )
                    break

        return results

    # =========================================================
    # PIPELINES
    # =========================================================

    def pipeline(
        self,
        key: str,
        *,
        context=None,
        shared_state=None,
    ):
        if key not in self._pipelines:
            raise KeyError(key)

        context = (
            context
            or ServiceContext()
        )

        shared_state = (
            shared_state or {}
        )

        results = {}

        for service in self._pipelines[key]:
            res = self.run(
                service,
                context=context,
                state=shared_state,
            )

            results[service] = res
            shared_state[
                service
            ] = res.result

        return results

    # =========================================================
    # LOOKUPS
    # =========================================================

    def group(
        self,
        name: str,
    ):
        return list(
            self._groups.get(
                name,
                set(),
            )
        )

    def scheduled(self):
        return list(
            self._scheduled.keys()
        )

    def history(
        self,
        key=None,
    ):
        if key is None:
            return self._results

        return [
            r
            for r in self._results
            if r.service == key
        ]

    # =========================================================
    # METRICS
    # =========================================================

    def metrics(self):
        base = super().metrics()

        successes = len(
            [
                r
                for r in self._results
                if r.success
            ]
        )

        failures = len(
            [
                r
                for r in self._results
                if not r.success
            ]
        )

        durations = [
            r.duration
            for r in self._results
            if r.duration
        ]

        avg = (
            sum(durations)
            / len(durations)
            if durations
            else 0
        )

        base.update(
            {
                "groups":
                    len(self._groups),
                "pipelines":
                    len(self._pipelines),
                "scheduled":
                    len(self._scheduled),
                "executions":
                    len(self._results),
                "successes":
                    successes,
                "failures":
                    failures,
                "average_duration":
                    round(avg, 4),
            }
        )

        return base

    # =========================================================
    # REPORT
    # =========================================================

    def report(self):
        return {
            "category":
                self.category,
            "health":
                self.health(),
            "metrics":
                self.metrics(),
            "services":
                self.export(),
        }


services = ServiceRegistry()