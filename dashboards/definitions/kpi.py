# dashboards/definitions/kpi.py

from __future__ import annotations

from dataclasses import dataclass

from .base import BaseDefinition


@dataclass(slots=True, frozen=True)
class KPIDefinition(
    BaseDefinition
):
    unit: str = ""
    precision: int = 2

    target: float | None = None
    warning: float | None = None
    critical: float | None = None

    formatter: str = ""