# dashboards/definitions/widget.py

from __future__ import annotations

from dataclasses import dataclass

from .base import BaseDefinition


@dataclass(slots=True, frozen=True)
class WidgetDefinition(
    BaseDefinition
):
    template: str = ""
    size: str = "md"

    refresh_interval: int = 300

    chart: str | None = None
    selector: str | None = None

    async_load: bool = False