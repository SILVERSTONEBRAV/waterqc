# core/registry_loader.py
import importlib
import logging
from django.apps import apps
from importlib.util import find_spec

logger = logging.getLogger(__name__)

_registry_loaded = False


def autodiscover_registry():
    global _registry_loaded

    if _registry_loaded:
        logger.debug("Registry already loaded in this process. Skipping.")
        return

    _registry_loaded = True

    for app_config in apps.get_app_configs():
        module_name = f"{app_config.name}.registry"

        try:
            if find_spec(module_name):
                importlib.import_module(module_name)
                logger.info("Loaded registry: %s", app_config.name)

        except Exception as e:
            logger.warning(
                "Registry load failed for %s: %s",
                app_config.name,
                e,
            )