# core/routing.py

from __future__ import annotations

import importlib
import logging
from collections import OrderedDict
from functools import lru_cache
from typing import Any

from django.apps import apps
from django.conf import settings
from django.urls import URLPattern, URLResolver

logger = logging.getLogger(__name__)


class RoutingRegistry:
    def __init__(self):
        self.loaded = OrderedDict()
        self.failed = OrderedDict()
        self.duplicates = OrderedDict()

    def mark_loaded(
        self,
        app_label: str,
        module: str,
        count: int,
    ):
        self.loaded[app_label] = {
            "module": module,
            "routes": count,
        }

    def mark_failed(
        self,
        app_label: str,
        module: str,
        exc: Exception,
    ):
        self.failed[app_label] = {
            "module": module,
            "error": str(exc),
        }

    def mark_duplicate(
        self,
        route: str,
        module: str,
    ):
        self.duplicates[route] = module

    def metrics(self):
        return {
            "loaded_apps": len(self.loaded),
            "failed_apps": len(self.failed),
            "duplicate_routes": len(
                self.duplicates
            ),
            "loaded": self.loaded,
            "failed": self.failed,
            "duplicates": self.duplicates,
        }


routing_state = RoutingRegistry()


def _route_key(
    pattern: URLPattern | URLResolver,
) -> str:
    try:
        return str(pattern.pattern)
    except Exception:
        return repr(pattern)


@lru_cache(maxsize=1)
def get_websocket_urlpatterns():
    patterns = []
    loaded_routes = set()

    for app_config in apps.get_app_configs():
        module_name = (
            f"{app_config.name}.routing"
        )

        try:
            module = importlib.import_module(
                module_name
            )

        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue

            logger.exception(
                "Failed importing %s",
                module_name,
            )

            routing_state.mark_failed(
                app_config.label,
                module_name,
                exc,
            )

            continue

        except Exception as exc:
            logger.exception(
                "Failed importing %s",
                module_name,
            )

            routing_state.mark_failed(
                app_config.label,
                module_name,
                exc,
            )

            continue

        app_patterns = getattr(
            module,
            "websocket_urlpatterns",
            (),
        )

        if not app_patterns:
            continue

        count = 0

        for pattern in app_patterns:
            route = _route_key(pattern)

            if route in loaded_routes:
                logger.warning(
                    "Duplicate websocket route ignored: %s",
                    route,
                )

                routing_state.mark_duplicate(
                    route,
                    module_name,
                )

                continue

            loaded_routes.add(route)
            patterns.append(pattern)
            count += 1

        routing_state.mark_loaded(
            app_config.label,
            module_name,
            count,
        )

        logger.info(
            "Loaded %s websocket routes from %s",
            count,
            module_name,
        )

    logger.info(
        "Loaded %s websocket routes from %s apps",
        len(patterns),
        len(routing_state.loaded),
    )

    return patterns


def rediscover_websocket_routes():
    get_websocket_urlpatterns.cache_clear()
    routing_state.loaded.clear()
    routing_state.failed.clear()
    routing_state.duplicates.clear()

    return get_websocket_urlpatterns()


def websocket_metrics():
    patterns = get_websocket_urlpatterns()

    return {
        "routes": len(patterns),
        **routing_state.metrics(),
    }


websocket_urlpatterns = (
    get_websocket_urlpatterns()
)