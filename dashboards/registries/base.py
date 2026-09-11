from __future__ import annotations

import hashlib
import inspect
import threading
import traceback
import weakref

from collections import OrderedDict, defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from graphlib import TopologicalSorter
from typing import Any, Callable, Iterable

from django.core.cache import cache
from django.utils import timezone


@dataclass(slots=True)
class RegistryItem:
    key: str
    obj: Any

    metadata: dict = field(default_factory=dict)

    aliases: set[str] = field(default_factory=set)
    tags: set[str] = field(default_factory=set)
    permissions: set[str] = field(default_factory=set)
    dependencies: set[str] = field(default_factory=set)

    enabled: bool = True
    singleton: bool = False
    lazy: bool = False
    priority: int = 0
    version: str = "1.0.0"

    created_at: datetime = field(default_factory=timezone.now)
    updated_at: datetime = field(default_factory=timezone.now)

    access_count: int = 0
    last_accessed: datetime | None = None

    status: str = "idle"
    error: str | None = None
    traceback: str | None = None

    execution_time: float = 0.0
    resolved_at: datetime | None = None

    instance: Any = None
    instance_lock: threading.RLock = field(
        default_factory=threading.RLock
    )

    def touch(self):
        self.last_accessed = timezone.now()
        self.access_count += 1


class BaseRegistry:
    category = "base"

    def __init__(
        self,
        *,
        max_workers: int = 16,
        parent: "BaseRegistry | None" = None,
    ):
        self.parent = parent

        self._items = OrderedDict()
        self._aliases = {}
        self._tags = defaultdict(set)
        self._permissions = defaultdict(set)
        self._metadata = defaultdict(set)

        self._dependencies = defaultdict(set)
        self._reverse_dependencies = defaultdict(set)

        self._events = defaultdict(list)
        self._history = deque(maxlen=10000)
        self._snapshots = OrderedDict()

        self._middlewares = []
        self._metrics = defaultdict(int)

        self._frozen = False
        self._lock = threading.RLock()

        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=self.category,
        )

    def freeze(self):
        self._frozen = True

    def unfreeze(self):
        self._frozen = False

    def on(self, event: str, callback: Callable):
        self._events[event].append(callback)

    def off(self, event: str, callback: Callable):
        self._events[event].remove(callback)

    def emit(self, event: str, payload=None):
        for cb in self._events.get(event, []):
            try:
                cb(payload)
            except Exception:
                pass

    def middleware(self, func: Callable):
        self._middlewares.append(func)
        return func

    def register(
        self,
        key: str,
        obj: Any,
        *,
        aliases: Iterable[str] = (),
        tags: Iterable[str] = (),
        permissions: Iterable[str] = (),
        dependencies: Iterable[str] = (),
        singleton: bool = False,
        lazy: bool = False,
        enabled: bool = True,
        priority: int = 0,
        version: str = "1.0.0",
        replace: bool = False,
        **metadata,
    ) -> RegistryItem:
        with self._lock:
            if self._frozen:
                raise RuntimeError("Registry is frozen")

            if key in self._items and not replace:
                raise ValueError(
                    f"{self.category}:{key} already exists"
                )

            item = RegistryItem(
                key=key,
                obj=obj,
                aliases=set(aliases),
                tags=set(tags),
                permissions=set(permissions),
                dependencies=set(dependencies),
                singleton=singleton,
                lazy=lazy,
                enabled=enabled,
                priority=priority,
                version=version,
                metadata=metadata,
            )

            self._items[key] = item

            for alias in aliases:
                self._aliases[alias] = key

            for tag in tags:
                self._tags[tag].add(key)

            for p in permissions:
                self._permissions[p].add(key)

            for k, v in metadata.items():
                self._metadata[f"{k}:{v}"].add(key)

            for dep in dependencies:
                self._dependencies[key].add(dep)
                self._reverse_dependencies[dep].add(key)

            self._history.append(
                (timezone.now(), "register", key)
            )

            self.emit("registered", item)

            return item

    def unregister(self, key: str):
        with self._lock:
            item = self.get(key)

            if not item:
                return False

            del self._items[item.key]

            for alias in item.aliases:
                self._aliases.pop(alias, None)

            for tag in item.tags:
                self._tags[tag].discard(item.key)

            for p in item.permissions:
                self._permissions[p].discard(item.key)

            self._dependencies.pop(item.key, None)
            self._reverse_dependencies.pop(item.key, None)

            self.invalidate_cache(item.key)

            self.emit("unregistered", item)

            return True

    def get(self, key, default=None):
        key = self._aliases.get(key, key)

        item = self._items.get(key)

        if item:
            return item

        if self.parent:
            return self.parent.get(key, default)

        return default

    def exists(self, key):
        return self.get(key) is not None

    def dependency_graph(self):
        return {
            k: list(v)
            for k, v in self._dependencies.items()
        }

    def topological_sort(self):
        graph = {
            k: set(v)
            for k, v in self._dependencies.items()
        }

        for k in self._items:
            graph.setdefault(k, set())

        return tuple(
            TopologicalSorter(graph).static_order()
        )

    @lru_cache(maxsize=1024)
    def cache_key(self, key):
        digest = hashlib.sha256(
            key.encode()
        ).hexdigest()

        return f"{self.category}:{digest}"

    def cache(self, key, value, timeout=300):
        cache.set(
            self.cache_key(key),
            value,
            timeout,
        )

    def cached(self, key):
        return cache.get(
            self.cache_key(key)
        )

    def invalidate_cache(self, key):
        cache.delete(
            self.cache_key(key)
        )

    def clear_cache(self):
        for key in self.keys():
            self.invalidate_cache(key)

    def resolve(self, key):
        item = self.get(key)

        if not item:
            raise KeyError(key)

        if not item.enabled:
            raise RuntimeError(
                f"{key} disabled"
            )

        item.touch()
        item.status = "resolving"

        started = timezone.now()

        try:
            if item.singleton:
                with item.instance_lock:
                    if item.instance is not None:
                        return item.instance

            if item.metadata.get("cache"):
                cached = self.cached(key)
                if cached is not None:
                    return cached

            obj = item.obj

            for mw in self._middlewares:
                obj = mw(item, obj)

            if inspect.isclass(obj):
                obj = obj()

            elif callable(obj):
                obj = obj()

            if item.singleton:
                item.instance = obj

            if item.metadata.get("cache"):
                self.cache(
                    key,
                    obj,
                    timeout=item.metadata.get(
                        "cache_timeout",
                        300,
                    ),
                )

            finished = timezone.now()

            item.status = "resolved"
            item.error = None
            item.traceback = None
            item.execution_time = (
                finished - started
            ).total_seconds()
            item.resolved_at = finished

            self._metrics["resolutions"] += 1

            self.emit("resolved", item)

            return obj

        except Exception as exc:
            item.status = "error"
            item.error = str(exc)
            item.traceback = traceback.format_exc()

            self._metrics["errors"] += 1

            self.emit(
                "error",
                {
                    "item": item,
                    "exception": exc,
                },
            )

            raise

    def resolve_many(
        self,
        keys: list[str],
    ):
        return {
            key: self.resolve(key)
            for key in self.topological_sort()
            if key in keys
        }

    def resolve_async(
        self,
        key: str,
    ) -> Future:
        return self.executor.submit(
            self.resolve,
            key,
        )

    def resolve_parallel(
        self,
        keys: list[str],
    ):
        futures = {
            k: self.resolve_async(k)
            for k in keys
        }

        return {
            k: f.result()
            for k, f in futures.items()
        }

    def search(self, query: str):
        query = query.lower()

        return [
            item
            for item in self._items.values()
            if (
                query in item.key.lower()
                or any(
                    query in x.lower()
                    for x in item.aliases
                )
                or any(
                    query in x.lower()
                    for x in item.tags
                )
            )
        ]

    def snapshot(self):
        data = self.export()

        self._snapshots[
            timezone.now().isoformat()
        ] = data

        return data

    def export(self):
        return {
            k: {
                "status": v.status,
                "enabled": v.enabled,
                "priority": v.priority,
                "version": v.version,
                "dependencies": list(
                    v.dependencies
                ),
                "tags": list(v.tags),
                "permissions": list(
                    v.permissions
                ),
                "metadata": v.metadata,
                "execution_time": (
                    v.execution_time
                ),
                "access_count": (
                    v.access_count
                ),
            }
            for k, v in self._items.items()
        }

    def metrics(self):
        return {
            "category": self.category,
            "items": len(self),
            "enabled": len(self.enabled()),
            "disabled": len(self.disabled()),
            "resolutions": self._metrics[
                "resolutions"
            ],
            "errors": self._metrics[
                "errors"
            ],
            "history": len(self._history),
            "events": len(self._events),
        }

    def health(self):
        return {
            "healthy": True,
            "metrics": self.metrics(),
            "cycles": False,
            "snapshots": len(
                self._snapshots
            ),
        }

    def enabled(self):
        return [
            i
            for i in self._items.values()
            if i.enabled
        ]

    def disabled(self):
        return [
            i
            for i in self._items.values()
            if not i.enabled
        ]

    def clear(self):
        self._items.clear()
        self._aliases.clear()
        self._tags.clear()
        self._permissions.clear()
        self._metadata.clear()
        self._dependencies.clear()
        self._reverse_dependencies.clear()

    def reset(self):
        self.clear()
        self._history.clear()
        self._snapshots.clear()
        self._metrics.clear()

    def keys(self):
        return list(self._items.keys())

    def values(self):
        return list(self._items.values())

    def items(self):
        return self._items.items()

    def shutdown(self):
        self.executor.shutdown(
            wait=False
        )

    @contextmanager
    def transaction(self):
        snapshot = self.snapshot()
        try:
            yield
        except Exception:
            self.reset()
            raise

    def __contains__(self, key):
        return self.exists(key)

    def __getitem__(self, key):
        item = self.get(key)

        if not item:
            raise KeyError(key)

        return item

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(
            self._items.values()
        )

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        self.shutdown()

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            f"category={self.category} "
            f"items={len(self)}>"
        )