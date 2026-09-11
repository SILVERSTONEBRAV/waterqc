from django.apps import AppConfig

class FilteredWaterConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'filtered_water'

    def ready(self):
        # Import signals to ensure they are registered when the app is ready
        import filtered_water.signals
