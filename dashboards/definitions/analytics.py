# dashboards/definitions/analytics.py

from __future__ import annotations

from dataclasses import dataclass

from .base import BaseDefinition


@dataclass(slots=True, frozen=True)
class AnalyticsDefinition(
    BaseDefinition
):
    query: str = ""

    materialized: bool = False
    refresh_interval: int = 3600

    datasource: str = "default"