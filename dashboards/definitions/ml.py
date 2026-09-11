# dashboards/definitions/ml.py

from __future__ import annotations

from dataclasses import dataclass

from .base import BaseDefinition


@dataclass(slots=True, frozen=True)
class MLDefinition(
    BaseDefinition
):
    algorithm: str = ""
    task: str = ""

    model_path: str = ""

    feature_store: str = ""

    retrainable: bool = True
    explainable: bool = True