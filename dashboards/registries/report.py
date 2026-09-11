from __future__ import annotations

import hashlib
import inspect
import traceback
from collections import defaultdict, deque
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from django.core.cache import cache
from django.utils import timezone
from django.utils.functional import cached_property

from .base import BaseRegistry


@dataclass(slots=True)
class ReportResult:
    report: str
    result: Any = None
    success: bool = True
    message: str | None = None
    started_at: datetime = field(
        default_factory=timezone.now
    )
    completed_at: datetime | None = None
    duration: float = 0.0
    metadata: dict = field(
        default_factory=dict
    )
    exception: str | None = None
    traceback: str | None = None


class ReportRegistry(BaseRegistry):
    category = "reports"

    def __init__(self):
        super().__init__()

        self._types = defaultdict(dict)

        self._templates = {}
        self._renderers = {}
        self._exporters = {}
        self._pipelines = {}
        self._schedulers = {}
        self._deliveries = {}
        self._validators = {}
        self._signers = {}
        self._watermarks = {}
        self._attachments = {}
        self._generators = {}
        self._hooks = {
            "before": defaultdict(list),
            "after": defaultdict(list),
            "error": defaultdict(list),
        }

        self._executions = defaultdict(list)
        self._history = deque(maxlen=10000)

    def register(
        self,
        key: str,
        obj: Any,
        *,
        report_type: str = "generic",
        format: str = "pdf",
        async_generation: bool = True,
        cache_timeout: int = 1800,
        version: str = "1.0.0",
        exportable: bool = True,
        schedulable: bool = True,
        signable: bool = False,
        cacheable: bool = True,
        singleton: bool = False,
        tags=None,
        permissions=None,
        dependencies=(),
        **metadata,
    ):
        metadata.update(
            {
                "report_type": report_type,
                "format": format,
                "version": version,
                "exportable": exportable,
                "schedulable": schedulable,
                "signable": signable,
                "async_generation": (
                    async_generation
                ),
                "cacheable": cacheable,
                "cache_timeout": cache_timeout,
            }
        )

        item = super().register(
            key=key,
            obj=obj,
            singleton=singleton,
            dependencies=dependencies,
            version=version,
            tags=tags or [],
            permissions=permissions or [],
            **metadata,
        )

        self._types[
            report_type
        ][key] = item

        return item

    def before(
        self,
        key: str,
        callback: Callable,
    ):
        self._hooks["before"][
            key
        ].append(callback)

    def after(
        self,
        key: str,
        callback: Callable,
    ):
        self._hooks["after"][
            key
        ].append(callback)

    def on_error(
        self,
        key: str,
        callback: Callable,
    ):
        self._hooks["error"][
            key
        ].append(callback)

    def _emit(
        self,
        hook: str,
        key: str,
        payload=None,
    ):
        for callback in self._hooks[
            hook
        ].get(key, []):
            try:
                callback(payload)
            except Exception:
                pass

    def register_template(
        self,
        name: str,
        fn: Callable,
    ):
        self._templates[name] = fn

    def render_template(
        self,
        name: str,
        **context,
    ):
        fn = self._templates.get(name)

        if fn is None:
            raise KeyError(name)

        return fn(**context)

    def register_generator(
        self,
        name: str,
        fn: Callable,
    ):
        self._generators[name] = fn

    def generate(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._generators.get(name)

        if fn is None:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    def register_exporter(
        self,
        name: str,
        fn: Callable,
    ):
        self._exporters[name] = fn

    def export_report(
        self,
        name: str,
        report,
        **kwargs,
    ):
        fn = self._exporters.get(name)

        if fn is None:
            raise KeyError(name)

        return fn(
            report,
            **kwargs,
        )

    def register_renderer(
        self,
        name: str,
        fn: Callable,
    ):
        self._renderers[name] = fn

    def render(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._renderers.get(name)

        if fn is None:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    def register_signer(
        self,
        name: str,
        fn: Callable,
    ):
        self._signers[name] = fn

    def sign(
        self,
        name: str,
        document,
        **kwargs,
    ):
        fn = self._signers.get(name)

        if fn is None:
            raise KeyError(name)

        return fn(
            document,
            **kwargs,
        )

    def register_delivery(
        self,
        name: str,
        fn: Callable,
    ):
        self._deliveries[name] = fn

    def deliver(
        self,
        name: str,
        report,
        **kwargs,
    ):
        fn = self._deliveries.get(name)

        if fn is None:
            raise KeyError(name)

        return fn(
            report,
            **kwargs,
        )

    def register_pipeline(
        self,
        name: str,
        fn: Callable,
    ):
        self._pipelines[name] = fn

    def pipeline(
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

    def register_validator(
        self,
        name: str,
        fn: Callable,
    ):
        self._validators[name] = fn

    def validate(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._validators.get(name)

        if fn is None:
            return True

        return fn(
            *args,
            **kwargs,
        )

    def register_watermark(
        self,
        name: str,
        fn: Callable,
    ):
        self._watermarks[name] = fn

    def register_attachment(
        self,
        name: str,
        fn: Callable,
    ):
        self._attachments[name] = fn

    def cache_key(
        self,
        key,
        *args,
        **kwargs,
    ):
        payload = (
            key
            + str(args)
            + str(kwargs)
        )

        return (
            "report:"
            + hashlib.sha256(
                payload.encode()
            ).hexdigest()
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
            item.metadata.get(
                "cacheable",
                True,
            )
            and not refresh
        ):
            cached = cache.get(
                cache_key
            )

            if cached is not None:
                return cached

        started = timezone.now()

        result = ReportResult(
            report=key
        )

        self._emit(
            "before",
            key,
            kwargs,
        )

        try:
            report = item.obj

            if inspect.isclass(report):
                report = report()

            if callable(report):
                value = report(
                    *args,
                    **kwargs,
                )
            else:
                value = report

            finished = timezone.now()

            result.result = value
            result.completed_at = (
                finished
            )
            result.duration = (
                finished - started
            ).total_seconds()

            self._executions[
                key
            ].append(finished)

            self._history.append(
                result
            )

            if item.metadata.get(
                "cacheable",
                True,
            ):
                cache.set(
                    cache_key,
                    result,
                    timeout=item.metadata.get(
                        "cache_timeout",
                        1800,
                    ),
                )

            self._emit(
                "after",
                key,
                result,
            )

            return result

        except Exception as exc:
            finished = timezone.now()

            result.success = False
            result.completed_at = finished
            result.duration = (
                finished - started
            ).total_seconds()
            result.exception = str(exc)
            result.traceback = (
                traceback.format_exc()
            )

            self._history.append(
                result
            )

            self._emit(
                "error",
                key,
                result,
            )

            raise

    def execute_async(
        self,
        key: str,
        *args,
        **kwargs,
    ) -> Future:
        return self.executor.submit(
            self.execute,
            key,
            *args,
            **kwargs,
        )

    def execute_parallel(
        self,
        keys: list[str],
    ):
        futures = {
            key: self.executor.submit(
                self.execute,
                key,
            )
            for key in keys
        }

        return {
            key: future.result()
            for key, future in futures.items()
        }

    def by_type(
        self,
        report_type,
    ):
        return self._types.get(
            report_type,
            {},
        )

    def history(
        self,
        key: str | None = None,
    ):
        if key is None:
            return list(
                self._history
            )

        return self._executions.get(
            key,
            [],
        )

    @cached_property
    def capabilities(self):
        return {
            "pdf": True,
            "excel": True,
            "word": True,
            "html": True,
            "csv": True,
            "json": True,
            "plotly": True,
            "scheduled_reports": True,
            "dashboard_snapshots": True,
            "email_delivery": True,
            "digital_signatures": True,
            "watermarks": True,
            "attachments": True,
            "templating": True,
            "async_generation": True,
            "batch_generation": True,
            "report_versioning": True,
            "caching": True,
            "parallel_execution": True,
        }

    def statistics(self):
        successful = len(
            [
                h
                for h in self._history
                if h.success
            ]
        )

        failed = len(
            [
                h
                for h in self._history
                if not h.success
            ]
        )

        durations = [
            h.duration
            for h in self._history
            if h.duration
        ]

        average = (
            sum(durations)
            / len(durations)
            if durations
            else 0
        )

        return {
            "reports": len(self),
            "types": {
                k: len(v)
                for k, v in self._types.items()
            },
            "templates": len(
                self._templates
            ),
            "renderers": len(
                self._renderers
            ),
            "exporters": len(
                self._exporters
            ),
            "pipelines": len(
                self._pipelines
            ),
            "deliveries": len(
                self._deliveries
            ),
            "validators": len(
                self._validators
            ),
            "signers": len(
                self._signers
            ),
            "executions": len(
                self._history
            ),
            "successes": successful,
            "failures": failed,
            "average_duration": round(
                average,
                4,
            ),
            "capabilities": (
                self.capabilities
            ),
            "timestamp": (
                timezone.now()
            ),
        }

    def health(self):
        return {
            "healthy": True,
            "metrics": self.statistics(),
            "registered": self.keys(),
        }

    def report(self):
        return {
            "category": self.category,
            "health": self.health(),
            "metrics": self.statistics(),
            "reports": self.export(),
        }


reports = ReportRegistry()