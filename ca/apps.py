# ca/apps.py

from django.apps import AppConfig


class CaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ca"

    def ready(self):
        from . import signals  # noqa: F401
