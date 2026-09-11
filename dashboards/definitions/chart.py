# dashboards/definitions/chart.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .base import BaseDefinition


@dataclass(slots=True, frozen=True)
class ChartDefinition(
    BaseDefinition
):
    chart_type: str = "plotly"

    renderer: str = "html"
    theme: str = "plotly"

    exportable: bool = True
    realtime: bool = False
    cacheable: bool = True

    width: int | None = None
    height: int | None = None

    builder: Callable | None = None
    exporter: Callable | None = None
    serializer: Callable | None = None

    animation: bool = True
    responsive: bool = True
    lazy: bool = False

    refresh_interval: int | None = None