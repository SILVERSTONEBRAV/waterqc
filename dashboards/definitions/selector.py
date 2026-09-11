# dashboards/definitions/selector.py

from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True, frozen=True)
class SelectorDefinition:
    key: str

    name: str

    resolver: Callable

    app_label: str = ""

    cacheable: bool = False

    timeout: int = 300

    description: str = ""

    permissions: tuple[str, ...] = ()