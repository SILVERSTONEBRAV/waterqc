from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.urls import reverse, NoReverseMatch
from django.shortcuts import resolve_url

logger = logging.getLogger(__name__)


class SuperUserEngine:
    DEFAULT_LANDING = "/"
    SESSION_GROUP = "SUPERUSER"

    @classmethod
    def is_superuser(cls, user) -> bool:
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and getattr(user, "is_active", False)
            and getattr(user, "is_superuser", False)
        )

    @classmethod
    def is_unrestricted(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def get_landing_target(cls) -> str:
        target = getattr(
            settings,
            "SUPERUSER_LANDING_MAP",
            cls.DEFAULT_LANDING,
        )

        if target is None:
            return cls.DEFAULT_LANDING

        target = str(target).strip()

        return target or cls.DEFAULT_LANDING

    @classmethod
    def get_landing_url(cls) -> str:
        target = cls.get_landing_target()

        try:
            if target.startswith("/"):
                return target

            try:
                return resolve_url(target)
            except Exception:
                return reverse(target)

        except NoReverseMatch:
            logger.exception(
                "SUPERUSER_LANDING_RESOLUTION_FAILED target=%s",
                target,
            )
            return cls.DEFAULT_LANDING

        except Exception:
            logger.exception(
                "SUPERUSER_LANDING_ERROR target=%s",
                target,
            )
            return cls.DEFAULT_LANDING

    @classmethod
    def landing_target(cls) -> str:
        return cls.get_landing_target()

    @classmethod
    def landing_url(cls) -> str:
        return cls.get_landing_url()

    @classmethod
    def resolve_redirect(cls, user, fallback=None) -> str:
        if cls.is_superuser(user):
            return cls.get_landing_url()

        return fallback or cls.DEFAULT_LANDING

    @classmethod
    def bypass_permissions(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_groups(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_dashboard_mapping(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_password_expiry(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_password_history(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_idle_timeout(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_session_limit(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_daily_login_limit(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_force_logout(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_mfa(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_risk_engine(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_plant_restrictions(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_section_restrictions(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_exports(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_audit_restrictions(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def bypass_workflow_restrictions(cls, user) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def allows(cls, user, policy: str) -> bool:
        return cls.is_superuser(user)

    @classmethod
    def initialize_session(cls, request, user):
        if not cls.is_superuser(user):
            return

        request.session.update(
            {
                "is_superuser": True,
                "superuser": True,
                "primary_group": cls.SESSION_GROUP,
                "groups": [cls.SESSION_GROUP],
                "superuser_landing": cls.get_landing_url(),
                "unrestricted": True,
                "permissions_bypass": True,
                "dashboard_bypass": True,
            }
        )

    @classmethod
    def validate(cls, user):
        if not cls.is_superuser(user):
            return False, "User is not a superuser"

        return True, None

    @classmethod
    def runtime_context(cls, user) -> dict[str, Any]:
        return {
            "is_superuser": True,
            "superuser": True,
            "groups": [cls.SESSION_GROUP],
            "primary_group": cls.SESSION_GROUP,
            "landing": cls.get_landing_url(),
            "default_landing": cls.get_landing_url(),
            "unrestricted": True,
            "bypass_permissions": True,
            "bypass_groups": True,
            "bypass_dashboard_mapping": True,
            "bypass_session_limit": True,
            "bypass_idle_timeout": True,
            "bypass_password_expiry": True,
            "bypass_password_history": True,
            "bypass_mfa": True,
            "bypass_risk_engine": True,
            "bypass_exports": True,
        }

    @classmethod
    def audit_payload(cls, user, request=None):
        ip = None

        if request:
            ip = (
                request.META.get("HTTP_X_FORWARDED_FOR")
                or request.META.get("HTTP_X_REAL_IP")
                or request.META.get("REMOTE_ADDR")
            )

        return {
            "user_id": getattr(user, "pk", None),
            "username": getattr(user, "username", None),
            "is_superuser": True,
            "landing": cls.get_landing_url(),
            "ip": ip,
        }

    @classmethod
    def diagnostics(cls, user) -> dict[str, Any]:
        return {
            "is_superuser": cls.is_superuser(user),
            "unrestricted": cls.is_unrestricted(user),
            "landing_target": cls.get_landing_target(),
            "landing_url": cls.get_landing_url(),
            "permissions_bypass": cls.bypass_permissions(user),
            "groups_bypass": cls.bypass_groups(user),
            "dashboard_bypass": cls.bypass_dashboard_mapping(user),
            "password_expiry_bypass": cls.bypass_password_expiry(user),
            "password_history_bypass": cls.bypass_password_history(user),
            "mfa_bypass": cls.bypass_mfa(user),
            "session_limit_bypass": cls.bypass_session_limit(user),
            "idle_timeout_bypass": cls.bypass_idle_timeout(user),
            "risk_engine_bypass": cls.bypass_risk_engine(user),
            "plant_bypass": cls.bypass_plant_restrictions(user),
            "section_bypass": cls.bypass_section_restrictions(user),
            "exports_bypass": cls.bypass_exports(user),
        }
