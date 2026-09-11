from django.utils import timezone


class SessionManagerV2:

    def __init__(self, remember_seconds: int):
        self.remember_seconds = remember_seconds

    def initialize(self, request, user, remember: bool):

        request.session.set_expiry(
            self.remember_seconds if remember else 0
        )

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