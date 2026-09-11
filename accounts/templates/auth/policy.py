import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AuthenticationPolicyV2:
    """
    Central rule engine for login validation.
    """

    def __init__(self, group_map: dict, max_attempts: int):
        self.group_map = group_map
        self.max_attempts = max_attempts

    def validate(self, user) -> Optional[tuple]:

        if getattr(user, "is_locked", False):
            return ("LOCKED", "Account locked")

        if not user.is_active:
            return ("INACTIVE", "Account inactive")

        if hasattr(user, "is_password_expired") and user.is_password_expired():
            return ("EXPIRED", "Password expired")

        groups = self._groups(user)

        if not groups:
            return ("NO_GROUP", "No group assigned")

        if not any(g in self.group_map for g in groups):
            return ("NO_MAPPING", "No dashboard mapping")

        return None

    def _groups(self, user):
        try:
            return sorted({
                g.upper().strip()
                for g in user.groups.values_list("name", flat=True)
            })
        except Exception:
            return []