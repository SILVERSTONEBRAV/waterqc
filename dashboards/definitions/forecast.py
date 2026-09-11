# dashboards/definitions/forecast.py

from __future__ import annotations

from dataclasses import dataclass

from .base import BaseDefinition


@dataclass(slots=True, frozen=True)
class ForecastDefinition(
    BaseDefinition
):
    model: str = "prophet"

    horizon: int = 30
    frequency: str = "D"

    confidence_interval: float = 0.95

    retrain_interval: int = 30