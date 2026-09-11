# sc/apps.py
from django.apps import AppConfig
import sys

class ScConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sc'

    def ready(self):
        # Avoid loading signals during migrations
        if 'migrate' in sys.argv:
            return
        from . import signals  # noqa
