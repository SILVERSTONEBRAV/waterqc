from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from functools import cached_property
from typing import Any

from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from .base import BaseRegistry, RegistryItem


class ForecastRegistry(BaseRegistry):
    category = "forecasts"

    def __init__(self):
        super().__init__()

        self._types = defaultdict(dict)
        self._targets = defaultdict(dict)
        self._engines = defaultdict(dict)
        self._versions = defaultdict(dict)
        self._horizons = defaultdict(dict)
        self._frequencies = defaultdict(dict)
        self._metrics = defaultdict(dict)

        self._lock = threading.RLock()
        self.executor = ThreadPoolExecutor(
            max_workers=8,
            thread_name_prefix=self.category,
        )

    def register(
        self,
        key: str,
        obj: Any,
        *,
        forecast_type: str = "general",
        target: str = "default",
        engine: str = "custom",
        version: str = "1.0.0",
        horizon: int = 30,
        frequency: str = "daily",
        ensemble: bool = False,
        probabilistic: bool = False,
        realtime: bool = False,
        retrainable: bool = True,
        cache_timeout: int = 3600,
        metrics=None,
        tags=None,
        aliases=None,
        permissions=None,
        dependencies=None,
        priority: int = 0,
        singleton: bool = True,
        lazy: bool = False,
        enabled: bool = True,
        replace: bool = False,
        **metadata,
    ) -> RegistryItem:
        metadata.update(
            {
                "forecast_type": forecast_type,
                "target": target,
                "engine": engine,
                "version": version,
                "horizon": horizon,
                "frequency": frequency,
                "ensemble": ensemble,
                "probabilistic": probabilistic,
                "realtime": realtime,
                "retrainable": retrainable,
                "cache_timeout": cache_timeout,
                "metrics": metrics or [],
            }
        )

        item = super().register(
            key=key,
            obj=obj,
            aliases=aliases or (),
            tags=tags or (),
            permissions=permissions or (),
            dependencies=dependencies or (),
            singleton=singleton,
            lazy=lazy,
            enabled=enabled,
            priority=priority,
            version=version,
            replace=replace,
            **metadata,
        )

        self._types[forecast_type][key] = item
        self._targets[target][key] = item
        self._engines[engine][key] = item
        self._versions[version][key] = item
        self._horizons[horizon][key] = item
        self._frequencies[frequency][key] = item

        for metric in metrics or []:
            self._metrics[metric][key] = item

        return item

    def cache_key(
        self,
        key: str,
        *args,
        **kwargs,
    ):
        payload = json.dumps(
            {
                "key": key,
                "args": str(args),
                "kwargs": str(kwargs),
            },
            sort_keys=True,
            default=str,
        )

        digest = hashlib.sha256(
            payload.encode()
        ).hexdigest()

        return f"{self.category}:{digest}"

    def get_cached(
        self,
        key,
        *args,
        **kwargs,
    ):
        return cache.get(
            self.cache_key(
                key,
                *args,
                **kwargs,
            )
        )

    def set_cached(
        self,
        value,
        key,
        *args,
        timeout=3600,
        **kwargs,
    ):
        cache.set(
            self.cache_key(
                key,
                *args,
                **kwargs,
            ),
            value,
            timeout,
        )

    def invalidate(
        self,
        key,
        *args,
        **kwargs,
    ):
        cache.delete(
            self.cache_key(
                key,
                *args,
                **kwargs,
            )
        )

    def generate(
        self,
        key: str,
        *args,
        refresh=False,
        **kwargs,
    ):
        item = self.get(key)

        if not item:
            raise KeyError(key)

        if not refresh:
            cached = self.get_cached(
                key,
                *args,
                **kwargs,
            )

            if cached is not None:
                return cached

        engine = self.resolve(key)

        if hasattr(engine, "forecast"):
            result = engine.forecast(
                *args,
                **kwargs,
            )
        elif hasattr(engine, "predict"):
            result = engine.predict(
                *args,
                **kwargs,
            )
        elif callable(engine):
            result = engine(
                *args,
                **kwargs,
            )
        else:
            result = engine

        self.set_cached(
            result,
            key,
            *args,
            timeout=item.metadata.get(
                "cache_timeout",
                3600,
            ),
            **kwargs,
        )

        return result

    def forecast(
        self,
        key: str,
        *args,
        **kwargs,
    ):
        return self.generate(
            key,
            *args,
            **kwargs,
        )

    def submit(
        self,
        key,
        *args,
        **kwargs,
    ) -> Future:
        return self.executor.submit(
            self.generate,
            key,
            *args,
            **kwargs,
        )

    def batch(
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

    def by_type(
        self,
        forecast_type,
    ):
        return self._types.get(
            forecast_type,
            {},
        )

    def by_target(
        self,
        target,
    ):
        return self._targets.get(
            target,
            {},
        )

    def by_engine(
        self,
        engine,
    ):
        return self._engines.get(
            engine,
            {},
        )

    def by_version(
        self,
        version,
    ):
        return self._versions.get(
            version,
            {},
        )

    def by_horizon(
        self,
        horizon,
    ):
        return self._horizons.get(
            horizon,
            {},
        )

    def by_frequency(
        self,
        frequency,
    ):
        return self._frequencies.get(
            frequency,
            {},
        )

    def by_metric(
        self,
        metric,
    ):
        return self._metrics.get(
            metric,
            {},
        )

    def filter(
        self,
        **criteria,
    ):
        results = []

        for item in self.enabled():
            matched = True

            for field, value in criteria.items():
                if item.metadata.get(field) != value:
                    matched = False
                    break

            if matched:
                results.append(item)

        return results

    def realtime(self):
        return self.filter(
            realtime=True
        )

    def ensembles(self):
        return self.filter(
            ensemble=True
        )

    def probabilistic(self):
        return self.filter(
            probabilistic=True
        )

    def retrainable(self):
        return self.filter(
            retrainable=True
        )

    def best_for_target(
        self,
        target,
    ):
        forecasts = list(
            self.by_target(
                target
            ).values()
        )

        if not forecasts:
            return None

        forecasts.sort(
            key=lambda x: (
                x.priority,
                x.metadata.get(
                    "version",
                    "0.0.0",
                ),
            ),
            reverse=True,
        )

        return forecasts[0]

    def retrain(
        self,
        key,
        *args,
        **kwargs,
    ):
        model = self.resolve(key)

        if hasattr(model, "fit"):
            return model.fit(
                *args,
                **kwargs,
            )

        if hasattr(model, "train"):
            return model.train(
                *args,
                **kwargs,
            )

        raise AttributeError(
            f"{key} does not support retraining."
        )

    @cached_property
    def capabilities(self):
        return {
            "prophet":
                importlib.util.find_spec(
                    "prophet"
                )
                is not None,
            "statsmodels":
                importlib.util.find_spec(
                    "statsmodels"
                )
                is not None,
            "sklearn":
                importlib.util.find_spec(
                    "sklearn"
                )
                is not None,
            "xgboost":
                importlib.util.find_spec(
                    "xgboost"
                )
                is not None,
            "lightgbm":
                importlib.util.find_spec(
                    "lightgbm"
                )
                is not None,
            "tensorflow":
                importlib.util.find_spec(
                    "tensorflow"
                )
                is not None,
            "torch":
                importlib.util.find_spec(
                    "torch"
                )
                is not None,
            "ensemble": True,
            "probabilistic": True,
            "multivariate": True,
            "realtime": True,
            "retraining": True,
        }

    def statistics(self):
        return {
            "total": len(self),
            "enabled": len(
                self.enabled()
            ),
            "disabled": len(
                self.disabled()
            ),
            "types": {
                k: len(v)
                for k, v in self._types.items()
            },
            "targets": {
                k: len(v)
                for k, v in self._targets.items()
            },
            "engines": {
                k: len(v)
                for k, v in self._engines.items()
            },
            "versions": {
                k: len(v)
                for k, v in self._versions.items()
            },
            "realtime": len(
                self.realtime()
            ),
            "ensembles": len(
                self.ensembles()
            ),
            "probabilistic": len(
                self.probabilistic()
            ),
            "retrainable": len(
                self.retrainable()
            ),
            "capabilities":
                self.capabilities,
            "timestamp":
                timezone.now(),
        }

    def schema(self):
        return json.loads(
            json.dumps(
                {
                    k: {
                        "forecast_type":
                            v.metadata.get(
                                "forecast_type"
                            ),
                        "target":
                            v.metadata.get(
                                "target"
                            ),
                        "engine":
                            v.metadata.get(
                                "engine"
                            ),
                        "version":
                            v.metadata.get(
                                "version"
                            ),
                        "horizon":
                            v.metadata.get(
                                "horizon"
                            ),
                        "frequency":
                            v.metadata.get(
                                "frequency"
                            ),
                        "ensemble":
                            v.metadata.get(
                                "ensemble"
                            ),
                        "probabilistic":
                            v.metadata.get(
                                "probabilistic"
                            ),
                        "realtime":
                            v.metadata.get(
                                "realtime"
                            ),
                        "retrainable":
                            v.metadata.get(
                                "retrainable"
                            ),
                        "priority":
                            v.priority,
                        "tags":
                            list(v.tags),
                        "permissions":
                            list(
                                v.permissions
                            ),
                    }
                    for k, v in self._items.items()
                },
                cls=DjangoJSONEncoder,
            )
        )


forecasts = ForecastRegistry()