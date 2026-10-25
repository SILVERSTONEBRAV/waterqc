from django.apps import AppConfig

class AlertsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "alerts"

    def ready(self):
        import alerts.signals  # ✅ safe place
        from django.db.models.signals import post_migrate

        def _on_post_migrate(sender, **kwargs):
            if sender.name == "alerts":
                try:
                    from .bootstrap import bootstrap_alerts_system
                    bootstrap_alerts_system()
                except Exception:
                    pass

        post_migrate.connect(_on_post_migrate, sender=self)
