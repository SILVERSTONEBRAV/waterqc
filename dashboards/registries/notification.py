from __future__ import annotations

import hashlib
import inspect
import json
import logging
import threading
from collections import defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from django.core.cache import cache
from django.utils import timezone
from django.utils.functional import cached_property

from .base import BaseRegistry, RegistryItem

logger = logging.getLogger(__name__)


class NotificationRegistry(BaseRegistry):
    category = "notifications"

    def __init__(self):
        super().__init__()

        self._channels: dict[str, dict[str, RegistryItem]] = defaultdict(dict)
        self._templates: dict[str, Callable] = {}
        self._renderers: dict[str, Callable] = {}
        self._formatters: dict[str, Callable] = {}
        self._dispatchers: dict[str, Callable] = {}
        self._fallbacks: dict[str, list[str]] = defaultdict(list)
        self._validators: dict[str, Callable] = {}
        self._rate_limiters: dict[str, Callable] = {}
        self._schedulers: dict[str, Callable] = {}
        self._hooks: dict[str, list[Callable]] = defaultdict(list)
        self._history: deque = deque(maxlen=10000)
        self._metrics = defaultdict(int)

        self._lock = threading.RLock()
        self.executor = ThreadPoolExecutor(
            max_workers=16,
            thread_name_prefix="notifications",
        )

    ####################################################################
    # REGISTRATION
    ####################################################################

    def register(
        self,
        key: str,
        obj: Any,
        *,
        channel: str = "default",
        priority: int = 0,
        async_delivery: bool = True,
        enabled: bool = True,
        retryable: bool = True,
        cache_timeout: int = 300,
        rate_limit: str | None = None,
        tags=None,
        permissions=None,
        version: str = "1.0.0",
        **metadata,
    ):
        metadata.update(
            {
                "channel": channel,
                "priority": priority,
                "async_delivery": async_delivery,
                "retryable": retryable,
                "cache_timeout": cache_timeout,
                "rate_limit": rate_limit,
            }
        )

        item = super().register(
            key=key,
            obj=obj,
            enabled=enabled,
            priority=priority,
            version=version,
            tags=tags or [],
            permissions=permissions or [],
            **metadata,
        )

        self._channels[channel][key] = item
        return item

    ####################################################################
    # TEMPLATE ENGINE
    ####################################################################

    def register_template(
        self,
        name: str,
        template: Callable,
    ):
        self._templates[name] = template

    def render_template(
        self,
        name: str,
        **context,
    ):
        fn = self._templates.get(name)

        if fn is None:
            raise KeyError(name)

        return fn(**context)

    ####################################################################
    # RENDERERS
    ####################################################################

    def register_renderer(
        self,
        name: str,
        renderer: Callable,
    ):
        self._renderers[name] = renderer

    def render(
        self,
        name: str,
        payload,
        **kwargs,
    ):
        renderer = self._renderers.get(name)

        if renderer is None:
            return payload

        return renderer(payload, **kwargs)

    ####################################################################
    # DISPATCHERS
    ####################################################################

    def register_dispatcher(
        self,
        name: str,
        fn: Callable,
    ):
        self._dispatchers[name] = fn

    def dispatch(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._dispatchers.get(name)

        if fn is None:
            raise KeyError(name)

        return fn(*args, **kwargs)

    ####################################################################
    # FORMATTERS
    ####################################################################

    def register_formatter(
        self,
        name: str,
        fn: Callable,
    ):
        self._formatters[name] = fn

    def format(
        self,
        name: str,
        payload,
        **kwargs,
    ):
        fn = self._formatters.get(name)

        if fn is None:
            return payload

        return fn(payload, **kwargs)

    ####################################################################
    # VALIDATORS
    ####################################################################

    def register_validator(
        self,
        name: str,
        fn: Callable,
    ):
        self._validators[name] = fn

    def validate_notification(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._validators.get(name)

        if fn is None:
            return True

        return bool(fn(*args, **kwargs))

    ####################################################################
    # RATE LIMITERS
    ####################################################################

    def register_rate_limiter(
        self,
        name: str,
        fn: Callable,
    ):
        self._rate_limiters[name] = fn

    def check_rate_limit(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._rate_limiters.get(name)

        if fn is None:
            return True

        return bool(fn(*args, **kwargs))

    ####################################################################
    # SCHEDULERS
    ####################################################################

    def register_scheduler(
        self,
        name: str,
        fn: Callable,
    ):
        self._schedulers[name] = fn

    def schedule(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        fn = self._schedulers.get(name)

        if fn is None:
            raise KeyError(name)

        return fn(*args, **kwargs)

    ####################################################################
    # FALLBACKS
    ####################################################################

    def register_fallback(
        self,
        channel: str,
        fallback: str,
    ):
        self._fallbacks[channel].append(
            fallback
        )

    def fallbacks(
        self,
        channel: str,
    ):
        return self._fallbacks.get(
            channel,
            [],
        )

    ####################################################################
    # HOOKS
    ####################################################################

    def register_hook(
        self,
        event: str,
        callback: Callable,
    ):
        self._hooks[event].append(
            callback
        )

    def emit(
        self,
        event: str,
        payload=None,
    ):
        super().emit(event, payload)

        for callback in self._hooks.get(
            event,
            [],
        ):
            try:
                callback(payload)
            except Exception:
                logger.exception(
                    "Notification hook failed."
                )

    ####################################################################
    # CACHE
    ####################################################################

    def cache_key(
        self,
        key,
        *args,
        **kwargs,
    ):
        payload = json.dumps(
            {
                "key": key,
                "args": args,
                "kwargs": kwargs,
            },
            default=str,
            sort_keys=True,
        )

        digest = hashlib.sha256(
            payload.encode()
        ).hexdigest()

        return (
            f"notifications:{digest}"
        )

    ####################################################################
    # CORE EXECUTION
    ####################################################################

    def _execute(
        self,
        sender,
        *args,
        **kwargs,
    ):
        if inspect.isclass(sender):
            sender = sender()

        if callable(sender):
            return sender(
                *args,
                **kwargs,
            )

        return sender

    ####################################################################
    # SEND
    ####################################################################

    def send(
        self,
        key: str,
        *args,
        refresh: bool = False,
        **kwargs,
    ):
        item = self.get(key)

        if item is None:
            raise KeyError(key)

        if not item.enabled:
            raise RuntimeError(
                f"{key} is disabled."
            )

        cache_key = self.cache_key(
            key,
            *args,
            **kwargs,
        )

        if not refresh:
            cached = cache.get(
                cache_key
            )
            if cached is not None:
                return cached

        if not self.validate_notification(
            key,
            *args,
            **kwargs,
        ):
            raise RuntimeError(
                f"Validation failed for {key}."
            )

        if not self.check_rate_limit(
            key,
            *args,
            **kwargs,
        ):
            raise RuntimeError(
                f"Rate limit exceeded for {key}."
            )

        self.emit(
            "before_send",
            {
                "key": key,
                "args": args,
                "kwargs": kwargs,
            },
        )

        started = timezone.now()

        try:
            result = self._execute(
                item.obj,
                *args,
                **kwargs,
            )

            cache.set(
                cache_key,
                result,
                item.metadata.get(
                    "cache_timeout",
                    300,
                ),
            )

            duration = (
                timezone.now() - started
            ).total_seconds()

            self._metrics["sent"] += 1

            self._history.append(
                {
                    "timestamp":
                        timezone.now(),
                    "key":
                        key,
                    "success":
                        True,
                    "duration":
                        duration,
                }
            )

            self.emit(
                "after_send",
                {
                    "key": key,
                    "result": result,
                },
            )

            return result

        except Exception as exc:
            self._metrics["failed"] += 1

            self._history.append(
                {
                    "timestamp":
                        timezone.now(),
                    "key":
                        key,
                    "success":
                        False,
                    "error":
                        str(exc),
                    "duration":
                        (
                            timezone.now()
                            - started
                        ).total_seconds(),
                }
            )

            self.emit(
                "send_error",
                {
                    "key": key,
                    "exception": exc,
                },
            )

            raise

    ####################################################################
    # ASYNC
    ####################################################################

    def send_async(
        self,
        key,
        *args,
        **kwargs,
    ) -> Future:
        return self.executor.submit(
            self.send,
            key,
            *args,
            **kwargs,
        )

    ####################################################################
    # BULK
    ####################################################################

    def send_many(
        self,
        key,
        recipients,
        *args,
        **kwargs,
    ):
        return [
            self.send(
                key,
                *args,
                recipient=recipient,
                **kwargs,
            )
            for recipient in recipients
        ]

    ####################################################################
    # BROADCAST
    ####################################################################

    def broadcast(
        self,
        channels,
        *args,
        **kwargs,
    ):
        results = {}

        for channel in channels:
            try:
                results[channel] = (
                    self.send(
                        channel,
                        *args,
                        **kwargs,
                    )
                )
            except Exception:
                logger.exception(
                    "Broadcast failed for %s",
                    channel,
                )

        return results

    ####################################################################
    # SEARCH
    ####################################################################

    def by_channel(
        self,
        channel=None,
    ):
        if channel:
            return self._channels.get(
                channel,
                {},
            )

        return dict(self._channels)

    def enabled_channels(self):
        return {
            k: v
            for k, v in self._items.items()
            if v.enabled
        }

    ####################################################################
    # HISTORY
    ####################################################################

    def history(
        self,
        limit: int = 100,
    ):
        return list(
            self._history
        )[-limit:]

    ####################################################################
    # CAPABILITIES
    ####################################################################

    @cached_property
    def capabilities(self):
        return {
            "email": True,
            "sms": True,
            "slack": True,
            "teams": True,
            "websocket": True,
            "push": True,
            "bulk": True,
            "broadcast": True,
            "templates": True,
            "fallbacks": True,
            "scheduling": True,
            "async_delivery": True,
            "audit_trail": True,
            "retry": True,
            "rate_limiting": True,
            "hooks": True,
            "caching": True,
        }

    ####################################################################
    # STATISTICS
    ####################################################################

    def statistics(self):
        return {
            "notifications":
                len(self),
            "channels":
                {
                    k: len(v)
                    for k, v in self._channels.items()
                },
            "templates":
                len(self._templates),
            "dispatchers":
                len(self._dispatchers),
            "validators":
                len(self._validators),
            "fallbacks":
                sum(
                    len(v)
                    for v in self._fallbacks.values()
                ),
            "hooks":
                {
                    k: len(v)
                    for k, v in self._hooks.items()
                },
            "sent":
                self._metrics["sent"],
            "failed":
                self._metrics["failed"],
            "capabilities":
                self.capabilities,
            "timestamp":
                timezone.now(),
        }

    ####################################################################
    # EXPORT
    ####################################################################

    def schema(self):
        return {
            k: {
                "channel":
                    v.metadata.get(
                        "channel"
                    ),
                "priority":
                    v.priority,
                "enabled":
                    v.enabled,
                "retryable":
                    v.metadata.get(
                        "retryable"
                    ),
                "async_delivery":
                    v.metadata.get(
                        "async_delivery"
                    ),
                "tags":
                    list(v.tags),
                "permissions":
                    list(v.permissions),
                "version":
                    v.version,
            }
            for k, v in self._items.items()
        }


notifications = NotificationRegistry()