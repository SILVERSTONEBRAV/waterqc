from django.apps import AppConfig

class QcConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'qc'

    def ready(self):
        import qc.tasks  # noqa
        import qc.signals  # noqa
