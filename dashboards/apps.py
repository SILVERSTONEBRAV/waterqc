# dashboards/apps.py
from django.apps import AppConfig


class DashboardsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboards"
    verbose_name = "Analytics Dashboard"

    def ready(self):
        try:
            import dashboards.signals  # noqa
        except Exception:
            pass