# dashboards/definitions/notification.py

from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True, frozen=True)
class NotificationDefinition:
    key: str
    name: str

    channel: str

    sender: Callable

    enabled: bool = True

    description: str = ""

    permissions: tuple[str, ...] = ()