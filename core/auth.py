from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework.exceptions import AuthenticationFailed
from typing import Optional, Tuple

class CookieJWTAuthentication(JWTAuthentication):
    """
    Extends JWTAuthentication to support tokens stored in HttpOnly cookies.
    Will first check the Authorization header, then fall back to 'access_token' cookie.
    """

    def authenticate(self, request) -> Optional[Tuple[object, object]]:
        # 1. Check Authorization Header
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
        else:
            # 2. Fall back to Cookie
            raw_token = request.COOKIES.get("access_token")

        if raw_token is None:
            return None  # No token provided

        try:
            validated_token = self.get_validated_token(raw_token)
        except InvalidToken:
            raise AuthenticationFailed("Invalid or expired token", code="authentication")

        return self.get_user(validated_token), validated_token
