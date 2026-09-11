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


class MLRegistry(BaseRegistry):
    category = "ml_models"

    def __init__(self):
        super().__init__()

        self._models: dict[str, dict[str, RegistryItem]] = defaultdict(dict)
        self._tasks: dict[str, dict[str, RegistryItem]] = defaultdict(dict)
        self._versions: dict[str, dict[str, RegistryItem]] = defaultdict(dict)

        self._pipelines: dict[str, Callable] = {}
        self._preprocessors: dict[str, Callable] = {}
        self._trainers: dict[str, Callable] = {}
        self._predictors: dict[str, Callable] = {}
        self._evaluators: dict[str, Callable] = {}
        self._feature_stores: dict[str, Callable] = {}
        self._embeddings: dict[str, Callable] = {}
        self._recommenders: dict[str, Callable] = {}
        self._anomaly_detectors: dict[str, Callable] = {}
        self._explainers: dict[str, Callable] = {}
        self._digital_twins: dict[str, Callable] = {}
        self._validators: dict[str, Callable] = {}
        self._serializers: dict[str, Callable] = {}

        self._version_history: dict[str, list[str]] = defaultdict(list)
        self._subscriptions: dict[str, set[str]] = defaultdict(set)

        self._lock = threading.RLock()

        self.executor = ThreadPoolExecutor(
            max_workers=16,
            thread_name_prefix="ml",
        )

    ####################################################################
    # REGISTRATION
    ####################################################################

    def register(
        self,
        key: str,
        obj: Any,
        *,
        model_type: str = "generic",
        task: str = "prediction",
        version: str = "1.0.0",
        online: bool = True,
        retrainable: bool = True,
        explainable: bool = False,
        distributed: bool = False,
        gpu: bool = False,
        cache_timeout: int = 1800,
        singleton: bool = True,
        lazy: bool = True,
        dependencies=None,
        tags=None,
        permissions=None,
        **metadata,
    ) -> RegistryItem:
        metadata.update(
            {
                "model_type": model_type,
                "task": task,
                "version": version,
                "online": online,
                "retrainable": retrainable,
                "explainable": explainable,
                "distributed": distributed,
                "gpu": gpu,
                "cache": True,
                "cache_timeout": cache_timeout,
            }
        )

        item = super().register(
            key,
            obj,
            singleton=singleton,
            lazy=lazy,
            dependencies=dependencies or [],
            tags=tags or [],
            permissions=permissions or [],
            version=version,
            **metadata,
        )

        self._models[model_type][key] = item
        self._tasks[task][key] = item
        self._versions[version][key] = item
        self._version_history[key].append(version)

        return item

    ####################################################################
    # COMPONENT REGISTRATION
    ####################################################################

    def register_pipeline(self, name: str, fn: Callable):
        self._pipelines[name] = fn

    def register_trainer(self, name: str, fn: Callable):
        self._trainers[name] = fn

    def register_predictor(self, name: str, fn: Callable):
        self._predictors[name] = fn

    def register_evaluator(self, name: str, fn: Callable):
        self._evaluators[name] = fn

    def register_preprocessor(self, name: str, fn: Callable):
        self._preprocessors[name] = fn

    def register_feature_store(self, name: str, fn: Callable):
        self._feature_stores[name] = fn

    def register_embedding(self, name: str, fn: Callable):
        self._embeddings[name] = fn

    def register_recommender(self, name: str, fn: Callable):
        self._recommenders[name] = fn

    def register_anomaly_detector(
        self,
        name: str,
        fn: Callable,
    ):
        self._anomaly_detectors[name] = fn

    def register_explainer(self, name: str, fn: Callable):
        self._explainers[name] = fn

    def register_digital_twin(self, name: str, fn: Callable):
        self._digital_twins[name] = fn

    def register_validator(self, name: str, fn: Callable):
        self._validators[name] = fn

    def register_serializer(self, name: str, fn: Callable):
        self._serializers[name] = fn

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

        return f"ml:{digest}"

    ####################################################################
    # MODEL RESOLUTION
    ####################################################################

    def load(self, key: str):
        item = self.get(key)

        if not item:
            raise KeyError(key)

        return self.resolve(key)

    ####################################################################
    # INFERENCE
    ####################################################################

    def predict(
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

        model = self.load(key)

        if inspect.isclass(model):
            model = model()

        if hasattr(model, "predict"):
            result = model.predict(
                *args,
                **kwargs,
            )
        elif callable(model):
            result = model(
                *args,
                **kwargs,
            )
        else:
            result = model

        cache.set(
            cache_key,
            result,
            item.metadata.get(
                "cache_timeout",
                1800,
            ),
        )

        item.touch()

        return result

    def predict_many(
        self,
        keys: list[str],
        *args,
        **kwargs,
    ):
        return {
            key: self.predict(
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
            self.predict,
            key,
            *args,
            **kwargs,
        )

    def predict_parallel(
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
    # TRAINING
    ####################################################################

    def train(
        self,
        trainer: str,
        *args,
        **kwargs,
    ):
        fn = self._trainers.get(trainer)

        if not fn:
            raise KeyError(trainer)

        return fn(
            *args,
            **kwargs,
        )

    def train_async(
        self,
        trainer: str,
        *args,
        **kwargs,
    ) -> Future:
        return self.executor.submit(
            self.train,
            trainer,
            *args,
            **kwargs,
        )

    ####################################################################
    # EVALUATION
    ####################################################################

    def evaluate(
        self,
        evaluator: str,
        *args,
        **kwargs,
    ):
        fn = self._evaluators.get(evaluator)

        if not fn:
            raise KeyError(evaluator)

        return fn(
            *args,
            **kwargs,
        )

    ####################################################################
    # PREPROCESSING
    ####################################################################

    def preprocess(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._preprocessors.get(name)

        if not fn:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    ####################################################################
    # PIPELINES
    ####################################################################

    def run_pipeline(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._pipelines.get(name)

        if not fn:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    ####################################################################
    # FEATURE STORE
    ####################################################################

    def feature_store(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._feature_stores.get(name)

        if not fn:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    ####################################################################
    # EMBEDDINGS
    ####################################################################

    def embedding(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._embeddings.get(name)

        if not fn:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    ####################################################################
    # EXPLAINABILITY
    ####################################################################

    def explain(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._explainers.get(name)

        if not fn:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    ####################################################################
    # RECOMMENDATIONS
    ####################################################################

    def recommend(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._recommenders.get(name)

        if not fn:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    ####################################################################
    # ANOMALY DETECTION
    ####################################################################

    def detect(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._anomaly_detectors.get(name)

        if not fn:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    ####################################################################
    # DIGITAL TWINS
    ####################################################################

    def digital_twin(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._digital_twins.get(name)

        if not fn:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    ####################################################################
    # VALIDATION / SERIALIZATION
    ####################################################################

    def validate(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._validators.get(name)

        if not fn:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    def serialize(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._serializers.get(name)

        if not fn:
            raise KeyError(name)

        return fn(
            *args,
            **kwargs,
        )

    ####################################################################
    # FILTERS
    ####################################################################

    def by_type(
        self,
        model_type: str,
    ):
        return self._models.get(
            model_type,
            {},
        )

    def by_task(
        self,
        task: str,
    ):
        return self._tasks.get(
            task,
            {},
        )

    def by_version(
        self,
        version: str,
    ):
        return self._versions.get(
            version,
            {},
        )

    def versions(
        self,
        key: str,
    ):
        return self._version_history.get(
            key,
            [],
        )

    def explainable(self):
        return {
            k: v
            for k, v in self._items.items()
            if v.metadata.get(
                "explainable"
            )
        }

    def online(self):
        return {
            k: v
            for k, v in self._items.items()
            if v.metadata.get(
                "online"
            )
        }

    def retrainable(self):
        return {
            k: v
            for k, v in self._items.items()
            if v.metadata.get(
                "retrainable"
            )
        }

    ####################################################################
    # CAPABILITIES
    ####################################################################

    @cached_property
    def capabilities(self):
        return {
            "classification": True,
            "regression": True,
            "clustering": True,
            "forecasting": True,
            "recommendations": True,
            "nlp": True,
            "embeddings": True,
            "transformers": True,
            "anomaly_detection": True,
            "root_cause_analysis": True,
            "digital_twins": True,
            "feature_store": True,
            "online_learning": True,
            "explainability": True,
            "retraining": True,
            "batch_inference": True,
            "realtime_inference": True,
            "async_training": True,
            "parallel_inference": True,
            "distributed_execution": True,
            "gpu_acceleration": True,
        }

    ####################################################################
    # STATISTICS
    ####################################################################

    def statistics(self):
        return {
            "models": len(self),
            "types": {
                k: len(v)
                for k, v in self._models.items()
            },
            "tasks": {
                k: len(v)
                for k, v in self._tasks.items()
            },
            "versions": {
                k: len(v)
                for k, v in self._versions.items()
            },
            "pipelines": len(self._pipelines),
            "trainers": len(self._trainers),
            "predictors": len(self._predictors),
            "evaluators": len(self._evaluators),
            "feature_stores": len(self._feature_stores),
            "embeddings": len(self._embeddings),
            "explainers": len(self._explainers),
            "recommenders": len(self._recommenders),
            "anomaly_detectors": len(
                self._anomaly_detectors
            ),
            "digital_twins": len(
                self._digital_twins
            ),
            "validators": len(
                self._validators
            ),
            "serializers": len(
                self._serializers
            ),
            "online": len(
                self.online()
            ),
            "retrainable": len(
                self.retrainable()
            ),
            "explainable": len(
                self.explainable()
            ),
            "capabilities": self.capabilities,
            "timestamp": timezone.now(),
        }

    ####################################################################
    # EXPORT
    ####################################################################

    def schema(self):
        return {
            k: {
                "model_type": v.metadata.get(
                    "model_type"
                ),
                "task": v.metadata.get(
                    "task"
                ),
                "version": v.metadata.get(
                    "version"
                ),
                "online": v.metadata.get(
                    "online"
                ),
                "retrainable": v.metadata.get(
                    "retrainable"
                ),
                "explainable": v.metadata.get(
                    "explainable"
                ),
                "distributed": v.metadata.get(
                    "distributed"
                ),
                "gpu": v.metadata.get(
                    "gpu"
                ),
                "tags": list(v.tags),
                "permissions": list(
                    v.permissions
                ),
                "dependencies": list(
                    v.dependencies
                ),
            }
            for k, v in self._items.items()
        }


ml_models = MLRegistry()