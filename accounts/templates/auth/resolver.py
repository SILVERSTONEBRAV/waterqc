import logging
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import resolve_url
from django.urls import NoReverseMatch

logger = logging.getLogger(__name__)


class RedirectResolverV3:

    def __init__(self, group_map: dict):
        # normalize ONCE at startup
        self.group_map = self._normalize_group_map(group_map)

    # =========================================================
    # MAIN ENTRY
    # =========================================================
    def resolve(self, user, request) -> str:

        try:
            # 1. superuser override
            if getattr(user, "is_superuser", False):
                return self._safe_resolve(
                    getattr(settings, "SUPERUSER_LANDING_MAP", "/")
                )

            # 2. session restore (priority order)
            for key in ("last_visited_url", "last_url", "last_module"):
                url = self._safe_url(request.session.get(key))
                if url:
                    return url

            # 3. group-based routing
            groups = self._get_groups(user)

            for g in groups:
                target = self.group_map.get(g)
                if target:
                    return self._safe_resolve(target)

            # 4. fallback
            return self._safe_resolve(
                getattr(settings, "DEFAULT_DASHBOARD_URL", "/")
            )

        except Exception as exc:
            logger.exception("REDIRECT_RESOLVER_FATAL user=%s error=%s", user, exc)
            return "/"

    # =========================================================
    # SAFE RESOLVE (never crashes auth flow)
    # =========================================================
    def _safe_resolve(self, target: str) -> str:

        if not target:
            logger.warning("EMPTY_REDIRECT_TARGET")
            return "/"

        target = str(target).strip()

        if not target:
            return "/"

        # direct path
        if target.startswith("/"):
            return target

        try:
            return resolve_url(target)

        except NoReverseMatch:
            logger.warning("INVALID_REDIRECT_TARGET target=%s", target)
            return "/"

    # =========================================================
    # SESSION SAFETY FILTER
    # =========================================================
    def _safe_url(self, url):
        if not url:
            return None

        try:
            url = str(url).strip()

            if not url:
                return None

            # must be internal path only
            if not url.startswith("/"):
                return None

            lowered = url.lower()

            blocked = (
                "//",
                "javascript:",
                "data:",
                "http:",
                "https:",
                "\\",
            )

            if any(b in lowered for b in blocked):
                logger.warning("BLOCKED_REDIRECT_URL url=%s", url)
                return None

            return url

        except Exception:
            return None

    # =========================================================
    # GROUP HANDLING (NORMALIZED + SAFE)
    # =========================================================
    def _get_groups(self, user):
        try:
            return sorted({
                str(g).strip().upper()
                for g in user.groups.values_list("name", flat=True)
            })
        except Exception:
            return []

    def _normalize_group_map(self, group_map: dict):
        normalized = {}

        for k, v in (group_map or {}).items():
            if not v:
                continue

            key = str(k).strip().upper()
            val = str(v).strip()

            if key:
                normalized[key] = val

        return normalized