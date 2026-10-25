from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "maintenance"
    label = "maintenance"
    verbose_name = "Maintenance"

    def ready(self):
        try:
            from .registry import bootstrap_maintenance_registry

            bootstrap_maintenance_registry()
        except Exception:
            pass
