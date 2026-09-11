import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from django.contrib.auth import authenticate, get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    user: Optional[User]
    error_code: Optional[str]
    message: Optional[str]


class AuthenticationEngineV2:
    """
    Stateless authentication core.
    No HTTP, no session, no rendering.
    """

    def authenticate_user(self, request, username: str, password: str) -> AuthResult:

        if not username or not password:
            return AuthResult(False, None, "EMPTY_CREDENTIALS", "Missing credentials")

        user = authenticate(request, username=username, password=password)

        if not user:
            return AuthResult(False, None, "INVALID_CREDENTIALS", "Invalid credentials")

        return AuthResult(True, user, None, None)