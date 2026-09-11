# core/managers.py
from typing import Tuple, Optional, Dict, Any
from django.contrib.auth.models import BaseUserManager
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError

from core.models import (
    validate_pf_number,
    validate_password_strength,
    validate_mobile_number,
)


class Luleti(BaseUserManager):

    def normalize_credentials(self, username: str, email: str) -> Tuple[str, str]:
        if not username or not email:
            raise ValueError("Username and email are required")

        username = username.strip().upper()
        email = self.normalize_email(email.strip())

        return username, email

    def sanitize_input(self, data: Dict[str, Any]) -> Dict[str, Any]:

        sanitized = {}

        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = value.strip()
            else:
                sanitized[key] = value

        return sanitized

    # -------------------------------
    # VALIDATION PIPELINE
    # -------------------------------
    def validate_credentials(
        self,
        username: str,
        password: Optional[str] = None,
        strict: bool = True,
    ):
        """
        Validate credentials with optional soft mode.
        """
        errors = []

        try:
            validate_pf_number(username)
        except ValidationError as e:
            errors.append(str(e))

        if password:
            try:
                validate_password_strength(password)
            except ValidationError as e:
                errors.append(str(e))

        if errors and strict:
            raise ValidationError(errors)

        return errors

    def validate_mobile(self, mobile: Optional[str], strict: bool = True):
        if not mobile:
            return []

        try:
            validate_mobile_number(mobile)
            return []
        except ValidationError as e:
            if strict:
                raise
            return [str(e)]

    # -------------------------------
    # PASSWORD HANDLING
    # -------------------------------
    def set_secure_password(self, instance, password: Optional[str]):
        """
        Apply password with validation + future hooks.
        """
        if not password:
            return

        validate_password_strength(password)

        # 🔥 future extension point
        self.pre_password_set(instance, password)

        instance.set_password(password)

        self.post_password_set(instance)

    def pre_password_set(self, instance, password: str):
        """Hook: enforce password history, blacklist, etc."""
        pass

    def post_password_set(self, instance):
        """Hook: audit logging, notifications, etc."""
        pass

    # -------------------------------
    # SAFE CREATION ENGINE
    # -------------------------------
    @transaction.atomic
    def create_instance(
        self,
        retry_on_conflict: bool = True,
        max_retries: int = 2,
        **validated_data,
    ):
        """
        Atomic + retry-safe instance creation.
        Prevents race-condition crashes.
        """
        attempt = 0

        while True:
            try:
                data = self.sanitize_input(validated_data)

                data = self.pre_create(**data)

                instance = self.model(**data)
                instance.full_clean()

                instance.save(using=self._db)

                return self.post_create(instance)

            except IntegrityError:
                if not retry_on_conflict or attempt >= max_retries:
                    raise
                attempt += 1

    # -------------------------------
    # BULK CREATION (ADVANCED)
    # -------------------------------
    @transaction.atomic
    def bulk_create_safe(self, objects_data: list[Dict[str, Any]]):
        """
        Bulk creation with validation and sanitization.
        """
        instances = []

        for data in objects_data:
            data = self.sanitize_input(data)
            instance = self.model(**data)
            instance.full_clean()
            instances.append(instance)

        created = self.model.objects.bulk_create(instances)

        for obj in created:
            self.post_create(obj)

        return created

    # -------------------------------
    # HOOK SYSTEM (EXTENSIBLE)
    # -------------------------------
    def pre_create(self, **kwargs):
        """
        Hook before instance creation.
        Modify incoming data here.
        """
        return kwargs

    def post_create(self, instance):

        return instance

    # -------------------------------
    # SECURITY EXTENSIONS (FUTURE)
    # -------------------------------
    def evaluate_risk(self, context: Optional[Dict[str, Any]] = None) -> float:

        return 0.0

    def enforce_security_policies(self, instance, context: Optional[Dict[str, Any]] = None):

        pass

    # -------------------------------
    # UTILITY METHODS
    # -------------------------------
    def safe_get_or_create(self, defaults=None, **kwargs):

        obj, created = self.get_or_create(defaults=defaults, **kwargs)

        if created:
            obj.full_clean()
            obj.save()

        return obj, created
