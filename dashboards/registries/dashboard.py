from __future__ import annotations

from collections import defaultdict
from functools import cached_property
from typing import Any

from .base import BaseRegistry, RegistryItem


class DashboardRegistry(BaseRegistry):
    category = "dashboards"

    def register(
        self,
        key: str,
        obj: Any,
        *,
        name: str | None = None,
        slug: str | None = None,
        icon: str = "fa-chart-line",
        group: str = "General",
        order: int = 0,
        url: str | None = None,
        description: str = "",
        public: bool = False,
        realtime: bool = False,
        permissions=None,
        tags=None,
        aliases=None,
        dependencies=None,
        enabled: bool = True,
        singleton: bool = False,
        lazy: bool = False,
        priority: int = 0,
        version: str = "1.0.0",
        replace: bool = False,
        **metadata,
    ) -> RegistryItem:
        metadata.update(
            {
                "name": name or key.replace(".", " ").title(),
                "slug": slug or key.replace(".", "-"),
                "icon": icon,
                "group": group,
                "order": order,
                "url": url,
                "description": description,
                "public": public,
                "realtime": realtime,
            }
        )

        return super().register(
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

    def filter(self, **criteria):
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

    def by_group(
        self,
        group: str | None = None,
    ):
        groups = defaultdict(list)

        for item in self.enabled():
            grp = item.metadata.get(
                "group",
                "General",
            )
            groups[grp].append(item)

        if group:
            return groups.get(group, [])

        return dict(groups)

    def by_category(
        self,
        category: str,
    ):
        return self.filter(category=category)

    def by_permission(
        self,
        permission: str,
    ):
        return super().by_permission(permission)

    def by_tag(
        self,
        tag: str,
    ):
        return super().by_tag(tag)

    def realtime(self):
        return self.filter(realtime=True)

    def public(self):
        return self.filter(public=True)

    def ordered(self):
        return sorted(
            self.enabled(),
            key=lambda x: (
                x.metadata.get("group", ""),
                x.metadata.get("order", 9999),
                x.priority,
                x.key,
            ),
        )

    def sidebar(self, user=None):
        data = []

        for item in self.ordered():
            permissions = set(item.permissions)

            if (
                user
                and permissions
                and not getattr(user, "is_superuser", False)
            ):
                if not user.has_perms(list(permissions)):
                    continue

            meta = item.metadata

            data.append(
                {
                    "key": item.key,
                    "name": meta.get(
                        "name",
                        item.key,
                    ),
                    "slug": meta.get(
                        "slug",
                        item.key,
                    ),
                    "icon": meta.get(
                        "icon",
                        "fa-chart-line",
                    ),
                    "group": meta.get(
                        "group",
                        "General",
                    ),
                    "badge": meta.get("badge"),
                    "url": meta.get("url"),
                    "description": meta.get(
                        "description",
                        "",
                    ),
                    "realtime": meta.get(
                        "realtime",
                        False,
                    ),
                    "public": meta.get(
                        "public",
                        False,
                    ),
                    "order": meta.get(
                        "order",
                        0,
                    ),
                }
            )

        return data

    def navigation_tree(self, user=None):
        tree = defaultdict(list)

        for dashboard in self.sidebar(user):
            tree[dashboard["group"]].append(dashboard)

        return dict(tree)

    def menu(self, user=None):
        return self.navigation_tree(user)

    def get_by_slug(
        self,
        slug: str,
    ):
        for item in self.enabled():
            if item.metadata.get("slug") == slug:
                return item

        return None

    def get_by_url(
        self,
        url: str,
    ):
        for item in self.enabled():
            if item.metadata.get("url") == url:
                return item

        return None

    def default_dashboard(
        self,
        user=None,
    ):
        dashboards = self.sidebar(user)

        if not dashboards:
            return None

        return dashboards[0]

    def search(
        self,
        query: str,
    ):
        query = query.lower().strip()

        results = []

        for item in self.enabled():
            meta = item.metadata

            name = meta.get(
                "name",
                "",
            ).lower()

            desc = meta.get(
                "description",
                "",
            ).lower()

            tags = " ".join(item.tags).lower()
            group = meta.get(
                "group",
                "",
            ).lower()

            if (
                query in item.key.lower()
                or query in name
                or query in desc
                or query in tags
                or query in group
            ):
                results.append(item)

        return results

    def favorites(self, user):
        if not hasattr(
            user,
            "dashboard_preferences",
        ):
            return []

        try:
            prefs = user.dashboard_preferences

            return [
                self.get(key)
                for key in getattr(
                    prefs,
                    "favorites",
                    [],
                )
                if self.get(key)
            ]
        except Exception:
            return []

    def user_dashboards(self, user):
        dashboards = []

        for item in self.enabled():
            permissions = set(item.permissions)

            if (
                not permissions
                or getattr(user, "is_superuser", False)
                or user.has_perms(list(permissions))
            ):
                dashboards.append(item)

        return dashboards

    def breadcrumbs(
        self,
        key: str,
    ):
        item = self.get(key)

        if not item:
            return []

        return [
            {
                "name": item.metadata.get(
                    "group",
                    "General",
                ),
                "type": "group",
            },
            {
                "name": item.metadata.get(
                    "name",
                    item.key,
                ),
                "type": "dashboard",
            },
        ]

    @cached_property
    def statistics(self):
        return {
            "total": len(self),
            "enabled": len(self.enabled()),
            "disabled": len(self.disabled()),
            "groups": len(
                self.by_group()
            ),
            "realtime": len(
                self.realtime()
            ),
            "public": len(
                self.public()
            ),
        }

    def schema(self):
        return {
            item.key: {
                "name": item.metadata.get(
                    "name"
                ),
                "slug": item.metadata.get(
                    "slug"
                ),
                "group": item.metadata.get(
                    "group"
                ),
                "icon": item.metadata.get(
                    "icon"
                ),
                "url": item.metadata.get(
                    "url"
                ),
                "description": item.metadata.get(
                    "description"
                ),
                "permissions": list(
                    item.permissions
                ),
                "tags": list(item.tags),
                "realtime": item.metadata.get(
                    "realtime",
                    False,
                ),
                "public": item.metadata.get(
                    "public",
                    False,
                ),
                "order": item.metadata.get(
                    "order",
                    0,
                ),
                "priority": item.priority,
                "version": item.version,
                "enabled": item.enabled,
            }
            for item in self.enabled()
        }

    def stats(self):
        return self.statistics

    def export_navigation(
        self,
        user=None,
    ):
        return {
            "tree": self.navigation_tree(user),
            "sidebar": self.sidebar(user),
            "default": self.default_dashboard(
                user
            ),
        }


dashboards = DashboardRegistry()