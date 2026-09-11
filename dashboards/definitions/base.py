# dashboards/definitions/base.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from django.utils.text import slugify


@dataclass(slots=True, frozen=True)
class BaseDefinition:
    key: str
    name: str

    description: str = ""

    icon: str = ""
    group: str = "General"

    order: int = 0
    enabled: bool = True
    realtime: bool = False

    permissions: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()

    cache_timeout: int = 300
    version: str = "1.0.0"

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def slug(self):
        return slugify(self.key)

    def as_dict(self):
        return {
            k: getattr(self, k)
            for k in self.__dataclass_fields__
        }