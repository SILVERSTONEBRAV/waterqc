from __future__ import annotations

import hashlib
import inspect
import json
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

import numpy as np
import pandas as pd
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db import connections
from django.utils import timezone

from .base import BaseRegistry, RegistryItem


@dataclass(slots=True)
class AnalyticsContext:
    params: dict = field(default_factory=dict)
    filters: dict = field(default_factory=dict)
    user: Any | None = None
    timeframe: str | None = None
    meta: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "params": self.params,
            "filters": self.filters,
            "user": getattr(self.user, "pk", None),
            "timeframe": self.timeframe,
            "meta": self.meta,
        }


@dataclass(slots=True)
class AnalyticsResult:
    key: str
    data: Any
    computed_at: datetime
    version: str
    fingerprint: str
    execution_time: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "key": self.key,
            "computed_at": self.computed_at.isoformat(),
            "version": self.version,
            "fingerprint": self.fingerprint,
            "execution_time": self.execution_time,
            "metadata": self.metadata,
        }


class AnalyticsRegistry(BaseRegistry):
    category = "analytics"

    def __init__(self):
        super().__init__()

        self._sql: dict[str, str] = {}
        self._features: set[str] = set()
        self._pipelines: dict[str, list[str]] = {}
        self._versions: dict[str, str] = {}
        self._materialized: set[str] = set()
        self._realtime: set[str] = set()
        self._lineage: dict[str, set[str]] = {}
        self._result_history: dict[str, list[AnalyticsResult]] = {}
        self._channel_layer = get_channel_layer()
        self._analytics_lock = threading.RLock()
        self.executor = ThreadPoolExecutor(
            max_workers=32,
            thread_name_prefix="analytics",
        )

    def register(
        self,
        key: str,
        obj: Any,
        *,
        sql: str | None = None,
        version: str = "1.0.0",
        dependencies: Iterable[str] = (),
        feature: bool = False,
        materialized: bool = False,
        realtime: bool = False,
        cache_ttl: int = 300,
        pipeline: Iterable[str] = (),
        **metadata,
    ) -> RegistryItem:
        metadata.update(
            {
                "sql": sql,
                "feature": feature,
                "materialized": materialized,
                "realtime": realtime,
                "cache_ttl": cache_ttl,
            }
        )

        item = super().register(
            key=key,
            obj=obj,
            dependencies=dependencies,
            version=version,
            **metadata,
        )

        if sql:
            self._sql[key] = sql

        self._versions[key] = version
        self._lineage[key] = set(dependencies)

        if feature:
            self._features.add(key)

        if materialized:
            self._materialized.add(key)

        if realtime:
            self._realtime.add(key)

        if pipeline:
            self._pipelines[key] = list(pipeline)

        return item

    def _fingerprint(
        self,
        key: str,
        context: AnalyticsContext,
        args,
        kwargs,
    ):
        payload = {
            "key": key,
            "context": context.to_dict(),
            "args": args,
            "kwargs": kwargs,
            "version": self._versions.get(key),
        }

        encoded = json.dumps(
            payload,
            default=str,
            sort_keys=True,
        ).encode()

        return hashlib.sha256(encoded).hexdigest()

    def _cache_key(
        self,
        key: str,
        fingerprint: str,
    ):
        return (
            f"analytics:"
            f"{self._versions.get(key,'1.0.0')}:"
            f"{key}:"
            f"{fingerprint}"
        )

    def _resolve_dependencies(
        self,
        key: str,
        ordered=None,
        seen=None,
        active=None,
    ):
        ordered = ordered or []
        seen = seen or set()
        active = active or set()

        if key in active:
            raise RuntimeError(
                f"Circular analytics dependency: {key}"
            )

        if key in seen:
            return ordered

        active.add(key)

        for dep in self._lineage.get(key, set()):
            if dep not in self:
                raise KeyError(
                    f"Missing dependency '{dep}' for '{key}'"
                )

            self._resolve_dependencies(
                dep,
                ordered,
                seen,
                active,
            )

        active.remove(key)
        seen.add(key)

        if key not in ordered:
            ordered.append(key)

        return ordered

    def _run_sql(
        self,
        sql: str,
        params=None,
    ) -> pd.DataFrame:
        params = params or {}

        with connections["default"].cursor() as cursor:
            cursor.execute(sql, params)
            columns = [c[0] for c in cursor.description]
            rows = cursor.fetchall()

        return pd.DataFrame(rows, columns=columns)

    def _execute(
        self,
        item: RegistryItem,
        context: AnalyticsContext,
        *args,
        **kwargs,
    ):
        obj = item.obj

        if item.metadata.get("sql"):
            return self._run_sql(
                item.metadata["sql"],
                context.params,
            )

        if inspect.isclass(obj):
            obj = obj()

        if callable(obj):
            sig = inspect.signature(obj)

            if "context" in sig.parameters:
                return obj(
                    context=context,
                    *args,
                    **kwargs,
                )

            return obj(*args, **kwargs)

        return obj

    def _compute(
        self,
        key: str,
        context: AnalyticsContext,
        *args,
        **kwargs,
    ):
        ordered = self._resolve_dependencies(key)

        results = {}

        for node_key in ordered:
            node = self.get(node_key)
            results[node_key] = self._execute(
                node,
                context,
                *args,
                **kwargs,
            )

        return results[key]

    def run(
        self,
        key: str,
        *,
        context: AnalyticsContext | None = None,
        refresh: bool = False,
        async_run: bool = False,
        **kwargs,
    ):
        context = context or AnalyticsContext()

        item = self.get(key)
        if not item:
            raise KeyError(key)

        fingerprint = self._fingerprint(
            key,
            context,
            (),
            kwargs,
        )

        cache_key = self._cache_key(
            key,
            fingerprint,
        )

        def execute():
            started = timezone.now()

            if not refresh:
                cached = cache.get(cache_key)
                if cached is not None:
                    return cached

            result = self._compute(
                key,
                context,
                **kwargs,
            )

            duration = (
                timezone.now() - started
            ).total_seconds()

            analytics_result = AnalyticsResult(
                key=key,
                data=result,
                computed_at=timezone.now(),
                version=self._versions.get(
                    key,
                    "1.0.0",
                ),
                fingerprint=fingerprint,
                execution_time=duration,
            )

            cache.set(
                cache_key,
                analytics_result,
                timeout=item.metadata.get(
                    "cache_ttl",
                    300,
                ),
            )

            self._result_history.setdefault(
                key,
                [],
            ).append(
                analytics_result
            )

            if key in self._realtime:
                self._broadcast(
                    key,
                    analytics_result,
                )

            return analytics_result

        if async_run:
            return self.executor.submit(execute)

        return execute()

    def run_many(
        self,
        keys: list[str],
        *,
        context: AnalyticsContext | None = None,
        refresh: bool = False,
    ):
        context = context or AnalyticsContext()

        futures = {
            key: self.executor.submit(
                self.run,
                key,
                context=context,
                refresh=refresh,
            )
            for key in keys
        }

        results = {}

        for key, future in futures.items():
            results[key] = future.result()

        return results

    def feature_vector(
        self,
        keys: list[str],
        context: AnalyticsContext | None = None,
    ):
        context = context or AnalyticsContext()

        return {
            key: self.run(
                key,
                context=context,
            ).data
            for key in keys
        }

    def dataframe(
        self,
        key: str,
        *,
        context: AnalyticsContext | None = None,
    ):
        result = self.run(
            key,
            context=context,
        ).data

        if isinstance(result, pd.DataFrame):
            return result

        return pd.DataFrame(result)

    def pipeline(
        self,
        key: str,
        *,
        context: AnalyticsContext | None = None,
    ):
        if key not in self._pipelines:
            raise KeyError(key)

        context = context or AnalyticsContext()

        output = {}

        for stage in self._pipelines[key]:
            output[stage] = self.run(
                stage,
                context=context,
            ).data

        return output

    def materialize(
        self,
        key: str,
        *,
        context: AnalyticsContext | None = None,
    ):
        return self.run(
            key,
            context=context,
            refresh=True,
        )

    def invalidate_materialized(
        self,
        key: str,
    ):
        prefix = f"analytics:{self._versions.get(key)}:{key}:"
        cache.delete_pattern(f"{prefix}*")

    def lineage(
        self,
        key: str,
    ):
        return {
            "dependencies": list(
                self._lineage.get(
                    key,
                    set(),
                )
            ),
            "version": self._versions.get(key),
            "feature": key in self._features,
            "materialized": key in self._materialized,
            "realtime": key in self._realtime,
        }

    def rolling(
        self,
        df: pd.DataFrame,
        column: str,
        window: int = 7,
    ):
        return df[column].rolling(window).mean()

    def growth(
        self,
        df: pd.DataFrame,
        column: str,
    ):
        return df[column].pct_change()

    def zscore(
        self,
        df: pd.DataFrame,
        column: str,
    ):
        return (
            df[column] - df[column].mean()
        ) / df[column].std()

    def anomaly(
        self,
        df: pd.DataFrame,
        column: str,
        threshold: float = 3.0,
    ):
        z = self.zscore(
            df,
            column,
        )

        return df[np.abs(z) > threshold]

    def correlation(
        self,
        df: pd.DataFrame,
    ):
        return df.corr(numeric_only=True)

    def describe(
        self,
        df: pd.DataFrame,
    ):
        return df.describe(
            include="all"
        )

    def forecast(
        self,
        df: pd.DataFrame,
        column: str,
        periods: int = 7,
    ):
        series = df[column].dropna()

        if len(series) < 2:
            return []

        slope = np.polyfit(
            np.arange(len(series)),
            series.values,
            1,
        )[0]

        last = series.iloc[-1]

        return [
            float(last + slope * i)
            for i in range(1, periods + 1)
        ]

    def _broadcast(
        self,
        key: str,
        result: AnalyticsResult,
    ):
        if not self._channel_layer:
            return

        try:
            async_to_sync(
                self._channel_layer.group_send
            )(
                "analytics_stream",
                {
                    "type": "analytics.update",
                    "data": {
                        "key": key,
                        "timestamp": timezone.now().isoformat(),
                        "payload": self._serialize(
                            result.data
                        ),
                    },
                },
            )
        except Exception:
            pass

    def _serialize(
        self,
        obj: Any,
    ):
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict("records")

        if isinstance(obj, pd.Series):
            return obj.to_dict()

        if isinstance(obj, np.ndarray):
            return obj.tolist()

        try:
            json.dumps(obj)
            return obj
        except Exception:
            return str(obj)

    def history(
        self,
        key: str,
    ):
        return self._result_history.get(
            key,
            [],
        )

    def stats(self):
        base = super().stats()

        base.update(
            {
                "analytics": len(self),
                "features": len(
                    self._features
                ),
                "materialized": len(
                    self._materialized
                ),
                "realtime": len(
                    self._realtime
                ),
                "versions": len(
                    self._versions
                ),
                "pipelines": len(
                    self._pipelines
                ),
            }
        )

        return base

    def report(self):
        return {
            "health": self.health(),
            "stats": self.stats(),
            "lineage": {
                k: self.lineage(k)
                for k in self.keys()
            },
        }


analytics = AnalyticsRegistry()