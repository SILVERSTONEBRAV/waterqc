from django.conf import settings
from django.utils import timezone


class SessionManagerV2:

    def __init__(self, remember_seconds: int):
        self.remember_seconds = remember_seconds

    def initialize(self, request, user, remember: bool):
        # Use the shared long-lived policy; a false remember flag must not turn
        # the cookie into a browser session.
        request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        request.session.cycle_key()

        request.session.update({
            "user_id": user.id,
            "username": user.username,
            "login_ts": timezone.now().timestamp(),
        })

        self._reset_lock(user)

    def _reset_lock(self, user):
        try:
            if hasattr(user, "reset_failed_login_attempts"):
                user.reset_failed_login_attempts()

            user.is_locked = False
            user.save(update_fields=["is_locked"])
        except Exception:
            pass
