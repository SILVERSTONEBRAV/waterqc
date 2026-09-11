import re
from django.core.exceptions import ValidationError
from .models import Configuration


class CustomPasswordValidator:
    def validate(self, password, user=None):
        config = Configuration.objects.first()

        if not config:
            raise ValidationError("Configuration settings are not defined.")

        self._validate_length(password, config)
        self._validate_digit(password, config)
        self._validate_uppercase(password, config)
        self._validate_lowercase(password, config)
        self._validate_special(password, config)

    def _validate_length(self, password, config):
        if len(password) < config.password_min_length:
            raise ValidationError(f"Password must be at least {config.password_min_length} characters long.")

    def _validate_digit(self, password, config):
        if config.password_require_digit and not re.findall(r'\d', password):
            raise ValidationError("Password must contain at least one digit.")

    def _validate_uppercase(self, password, config):
        if config.password_require_uppercase and not re.findall(r'[A-Z]', password):
            raise ValidationError("Password must contain at least one uppercase letter.")

    def _validate_lowercase(self, password, config):
        if config.password_require_lowercase and not re.findall(r'[a-z]', password):
            raise ValidationError("Password must contain at least one lowercase letter.")

    def _validate_special(self, password, config):
        if config.password_require_special and not re.findall(r'[^A-Za-z0-9]', password):
            raise ValidationError("Password must contain at least one special character.")

    def _validate_pf_number(self, pf_number, config):
        if not pf_number.startswith(config.pf_prefix):
            raise ValidationError(f"PF number must start with '{config.pf_prefix}'")
        if not pf_number[len(config.pf_prefix):].isdigit() or len(
                pf_number[len(config.pf_prefix):]) != config.pf_length:
            raise ValidationError(
                f"PF number must be in the format '{config.pf_prefix}{'X' * config.pf_length}' with 'X' being digits")

    def get_help_text(self):
        return "Your password must follow the configured policy."
