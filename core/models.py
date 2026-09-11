# core/models.py

import logging
import re
from datetime import timedelta
from typing import Optional, Any
from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.core.cache import cache

logger = logging.getLogger(__name__)
class Section(models.Model):
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Section"
        verbose_name_plural = "Sections"

    def __str__(self) -> str:
        return self.name


# -------------------------------
# System Configuration (Singleton)
# -------------------------------
class SystemConfiguration(models.Model):
    """
    Centralized runtime configuration.
    Enforced singleton (id=1).
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    # Password Policy
    password_min_length = models.PositiveIntegerField(default=8)
    password_require_digit = models.BooleanField(default=True)
    password_require_uppercase = models.BooleanField(default=True)
    password_require_lowercase = models.BooleanField(default=True)
    password_require_special = models.BooleanField(default=True)
    password_history_count = models.PositiveIntegerField(default=10)
    password_expire_days = models.PositiveIntegerField(default=90)

    # Session Policy
    session_timeout_minutes = models.PositiveIntegerField(default=30)
    session_idle_logout_minutes = models.PositiveIntegerField(default=15)
    daily_login_limit_minutes = models.PositiveIntegerField(default=480)
    max_concurrent_sessions = models.PositiveIntegerField(default=3)
    paginate_by = models.PositiveIntegerField(default=20, help_text="Default number of items per page in list views")
    # Cache
    cache_timeout_seconds = models.PositiveIntegerField(default=3600)

    # Security / MFA
    adaptive_mfa_enabled = models.BooleanField(default=True)
    adaptive_risk_threshold = models.FloatField(default=50.0)
    require_2fa_for_high_risk = models.BooleanField(default=True)

    # Audit
    audit_log_retention_days = models.PositiveIntegerField(default=365)
    log_data_exports = models.BooleanField(default=True)
    log_anomalies = models.BooleanField(default=True)

    # Identity Rules
    email_domain = models.CharField(max_length=50, default="nairobiwater.co.ke")
    pf_prefix = models.CharField(max_length=10, default="NCWSC")
    pf_length = models.PositiveIntegerField(default=5)
    mobile_number_regex = models.CharField(max_length=50, default=r"^\+254\d{9}$")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Configuration"
        verbose_name_plural = "System Configuration"

    def save(self, *args, **kwargs):
        """Enforce singleton strictly."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def current(cls) -> "SystemConfiguration":
        # Always fetch fresh instance to avoid caching stale settings
        return cls.objects.get_or_create(pk=1)[0]

    def __str__(self):
        return "System Configuration"


# -------------------------------
# Validators (Config-driven)
# -------------------------------
def validate_pf_number(value: Optional[str]) -> None:
    if not value:
        return
    config = SystemConfiguration.current()
    pattern = f"^{config.pf_prefix}\\d{{{config.pf_length}}}$"
    if not re.match(pattern, value):
        raise ValidationError(
            f"PF number must match '{config.pf_prefix}' + {config.pf_length} digits"
        )


def validate_mobile_number(value: Optional[str]) -> None:
    if not value:
        return
    config = SystemConfiguration.current()
    if not re.match(config.mobile_number_regex, value):
        raise ValidationError("Invalid mobile number format")


def validate_password_strength(value: str) -> None:
    config = SystemConfiguration.current()

    if len(value) < config.password_min_length:
        raise ValidationError(f"Minimum length is {config.password_min_length}")

    if config.password_require_digit and not any(c.isdigit() for c in value):
        raise ValidationError("Must include a digit")

    if config.password_require_uppercase and not any(c.isupper() for c in value):
        raise ValidationError("Must include uppercase letter")

    if config.password_require_lowercase and not any(c.islower() for c in value):
        raise ValidationError("Must include lowercase letter")

    if config.password_require_special and not any(c in "!@#$%^&*()_+-=" for c in value):
        raise ValidationError("Must include special character")


# -------------------------------
# Audit Log
# -------------------------------
class AuditLogEntry(models.Model):
    ACTION_CHOICES = [
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("DELETE", "Delete"),
        ("LOGIN", "Login"),
        ("LOGOUT", "Logout"),
        ("EXPORT", "Export"),
        ("SECURITY", "Security"),
        ("SESSION", "Session"),
    ]

    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=128, blank=True)
    description = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.action} - {self.model_name} ({self.timestamp})"


# -------------------------------
# IP Restriction
# -------------------------------
class IPRestriction(models.Model):
    name = models.CharField(max_length=100, unique=True)
    ip_range_start = models.GenericIPAddressField()
    ip_range_end = models.GenericIPAddressField()
    description = models.TextField(blank=True)

    def contains_ip(self, ip: str) -> bool:
        import ipaddress
        return ipaddress.IPv4Address(self.ip_range_start) <= ipaddress.IPv4Address(ip) <= ipaddress.IPv4Address(self.ip_range_end)

    def __str__(self):
        return self.name


# -------------------------------
# User Session Tracking
# -------------------------------
class UserSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions")
    session_key = models.CharField(max_length=40, unique=True, db_index=True)
    login_time = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    terminated = models.BooleanField(default=False)

    class Meta:
        ordering = ["-login_time"]

    def is_expired(self) -> bool:
        """Dynamic session expiry based on latest config"""
        config = SystemConfiguration.current()
        timeout = timedelta(minutes=config.session_timeout_minutes)
        return self.last_activity + timeout < timezone.now()

    def update_activity(self):
        """Update last activity timestamp dynamically"""
        self.last_activity = timezone.now()
        self.save(update_fields=["last_activity"])

    def __str__(self):
        return f"{self.user} - {self.session_key}"


class UserPasswordHistory(models.Model):
    """Historical passwords to enforce reuse policies"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_history")
    password_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "User Password History"
        verbose_name_plural = "User Password Histories"

    def __str__(self):
        return f"{self.user} - {self.created_at}"


# -------------------------------
# Settings Manager (Dynamic)
# -------------------------------
class SettingsManager:

    @staticmethod
    def get_config() -> SystemConfiguration:
        # Always fetch fresh configuration to avoid caching issues
        return SystemConfiguration.current()

    @classmethod
    def session_timeout(cls) -> int:
        return cls.get_config().session_timeout_minutes

    @classmethod
    def idle_logout(cls) -> int:
        return cls.get_config().session_idle_logout_minutes

    @classmethod
    def daily_login_limit(cls) -> int:
        return cls.get_config().daily_login_limit_minutes

    @classmethod
    def max_sessions(cls) -> int:
        return cls.get_config().max_concurrent_sessions

    @classmethod
    def cache_timeout(cls) -> int:
        return cls.get_config().cache_timeout_seconds


# -------------------------------
# Signals
# -------------------------------
def create_audit_log(sender, instance, action: str):
    try:
        AuditLogEntry.objects.create(
            action=action,
            model_name=sender.__name__,
            object_id=str(getattr(instance, "pk", "")),
            description=str(instance),
        )
    except Exception as e:
        logger.error(f"Audit log failed: {e}")


@receiver(post_save)
def audit_save(sender, instance, created, **kwargs):
    if sender in [SystemConfiguration, Section, IPRestriction]:
        create_audit_log(sender, instance, "CREATE" if created else "UPDATE")


@receiver(post_delete)
def audit_delete(sender, instance, **kwargs):
    if sender in [SystemConfiguration, Section, IPRestriction]:
        create_audit_log(sender, instance, "DELETE")


@receiver(user_logged_in)
def track_login(sender, request, user, **kwargs):
    now = timezone.now()
    max_sessions = SettingsManager.max_sessions()
    active_sessions = UserSession.objects.filter(user=user, terminated=False)

    # Terminate oldest session if over limit
    if active_sessions.count() >= max_sessions:
        oldest = active_sessions.order_by("login_time").first()
        if oldest:
            oldest.terminated = True
            oldest.save(update_fields=["terminated"])

    # Create current session
    UserSession.objects.create(user=user, session_key=request.session.session_key)


@receiver(user_logged_out)
def track_logout(sender, request, user, **kwargs):
    UserSession.objects.filter(user=user, session_key=request.session.session_key).update(terminated=True)


# -------------------------------
# Cache Utilities (Dynamic)
# -------------------------------
def cache_set(key: str, value: Any, timeout: Optional[int] = None):
    """Dynamic cache set using current system config"""
    config_timeout = timeout or SettingsManager.cache_timeout()
    cache.set(key, value, config_timeout)


def cache_get(key: str):
    """Dynamic cache get"""
    return cache.get(key)
