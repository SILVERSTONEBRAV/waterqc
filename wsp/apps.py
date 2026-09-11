from django.apps import AppConfig


class WspConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wsp'

    def ready(self):
        # Import signals so Django registers them
        import wsp.signals  # noqa: F401
