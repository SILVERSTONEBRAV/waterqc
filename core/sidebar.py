
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from django.core.cache import cache


@dataclass(slots=True)
class SidebarItem:
    key: str
    label: str
    icon: str
    url: str
    badge: int = 0
    order: int = 100
    favorite: bool = False
    pinned: bool = False
    children: list[Any] = field(default_factory=list)
    capabilities: dict[str, bool] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)


class SidebarBuilder:

    CACHE_SECONDS = 300

    def __init__(self, registry):
        self.registry = registry

    def _permission_signature(self, user):
        if user.is_superuser:
            return "superuser"

        groups = tuple(
            user.groups.values_list("pk", flat=True)
        )

        permissions = tuple(
            user.user_permissions.values_list(
                "content_type_id",
                "codename",
            )
        )

        return hash((groups, permissions))

    def _cache_key(self, request):
        user = request.user

        if not user.is_authenticated:
            return "sidebar:anonymous"

        signature = self._permission_signature(user)

        return (
            f"sidebar:"
            f"{user.pk}:"
            f"{signature}"
        )

    def _build_child(self, child):
        capabilities = dict(
            child.get("capabilities") or {}
        )

        if not capabilities.get("view", True):
            return None

        children = [
            built
            for nested in child.get("children", [])
            if (built := self._build_child(nested)) is not None
        ]

        return SidebarItem(
            key=child["key"],
            label=child.get("label", child["key"]),
            icon=child.get("icon", "circle"),
            url=child.get("url", "#"),
            badge=child.get("badge", 0),
            order=child.get("order", 100),
            favorite=child.get("favorite", False),
            pinned=child.get("pinned", False),
            children=children,
            capabilities=capabilities,
            actions=list(child.get("actions", [])),
        )

    def _build_item(self, model):
        capabilities = dict(
            model.get("capabilities") or {}
        )

        if not capabilities.get("view", True):
            return None

        children = [
            child
            for raw_child in model.get("children", [])
            if (child := self._build_child(raw_child)) is not None
        ]

        routes = model.get("routes") or {}

        return SidebarItem(
            key=model["key"],
            label=model.get("label", model["key"]),
            icon=model.get("icon", "circle"),
            url=routes.get("list") or "#",
            badge=model.get("badge", 0),
            order=model.get("order", 100),
            favorite=model.get("favorite", False),
            pinned=model.get("pinned", False),
            children=children,
            capabilities=capabilities,
            actions=list(model.get("actions", [])),
        )

    def _sort_items(self, items):
        items.sort(
            key=lambda item: (
                not item.pinned,
                not item.favorite,
                item.order,
                item.label.casefold(),
            )
        )

        for item in items:
            self._sort_items(item.children)

        return items

    def build(self, request):
        user = request.user

        if not user.is_authenticated:
            return []

        cache_key = self._cache_key(request)

        cached = cache.get(cache_key)

        if cached is not None:
            return cached

        registry_sidebar = self.registry.sidebar(request)

        groups = defaultdict(list)

        for app, models in registry_sidebar.items():

            for model in models:

                item = self._build_item(model)

                if item is None:
                    continue

                group_name = (
                    model.get("group")
                    or app
                )

                groups[group_name].append(item)

        sidebar = []

        for group, items in groups.items():

            if not items:
                continue

            self._sort_items(items)

            sidebar.append(
                {
                    "group": group,
                    "items": items,
                }
            )

        sidebar.sort(
            key=lambda item: item["group"].casefold()
        )

        cache.set(
            cache_key,
            sidebar,
            self.CACHE_SECONDS,
        )

        return sidebar

    def invalidate(self, user=None):
        if user is None:
            cache.clear()
            return

        delete_pattern = getattr(
            cache,
            "delete_pattern",
            None,
        )

        if delete_pattern:
            delete_pattern(
                f"sidebar:{user.pk}:*"
            )
