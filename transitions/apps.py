from django.apps import AppConfig


class TransitionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'transitions'

    def ready(self):
        from .signals import connect_signals
        connect_signals()
