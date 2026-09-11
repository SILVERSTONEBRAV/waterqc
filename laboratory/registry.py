# laboratory/registry.py

import logging
import re
from typing import Any, Dict, Optional, Type

from django.apps import apps
from django.db.models import Model

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "laboratory"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================

def get_model(model_name: str) -> Type[Model]:
    """
    Lazy resolver for laboratory models.
    Prevents circular imports with accounts, t, and user-group relations.
    """
    try:
        return apps.get_model(APP_LABEL, model_name)
    except Exception as e:
        logger.error(f"[laboratory.registry] Failed to resolve {model_name}: {e}")
        raise


# ==========================================================
# KEY + LABEL HELPERS
# ==========================================================

def _key(model: Type[Model]) -> str:
    return f"{model._meta.app_label}.{model._meta.model_name}"


def _humanize(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name).strip()


# ==========================================================
# REGISTRY CORE
# ==========================================================

class LaboratoryRegistry:
    """
    Registry for laboratory domain.

    Focus:
    - lab identity (Laboratory)
    - user access mapping
    - role/group resolution
    - plant-bound lab structure
    """

    def __init__(self):
        self._registry: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------
    # REGISTER MODEL
    # ------------------------------------------------------
    def register(self, model: Type[Model], **config) -> None:
        key = _key(model)

        if key in self._registry:
            return

        meta = {
            "key": key,
            "app_label": model._meta.app_label,
            "model_name": model._meta.model_name,
            "verbose_name": str(model._meta.verbose_name),
            "verbose_name_plural": str(model._meta.verbose_name_plural),
            "human_name": _humanize(model.__name__),

            # laboratory-specific capabilities
            "is_lab_core": config.get("is_lab_core", False),
            "is_user_bound": config.get("is_user_bound", False),
            "is_plant_bound": config.get("is_plant_bound", False),

            # functional hooks (UI/API binding)
            "hooks": config.get("hooks", {}),
        }

        self._registry[key] = meta

        logger.info(f"[laboratory.registry] Registered {key}")

        # sync to global registry
        try:
            register_model(model, **meta)
        except Exception as e:
            logger.warning(f"[laboratory.registry] global sync failed for {key}: {e}")

    # ------------------------------------------------------
    # GET
    # ------------------------------------------------------
    def get(self, model: Type[Model]) -> Optional[Dict[str, Any]]:
        return self._registry.get(_key(model))

    # ------------------------------------------------------
    # ALL
    # ------------------------------------------------------
    def all(self) -> Dict[str, Dict[str, Any]]:
        return self._registry

    # ------------------------------------------------------
    # FILTER
    # ------------------------------------------------------
    def filter(self, **criteria) -> Dict[str, Dict[str, Any]]:
        results = {}

        for k, v in self._registry.items():
            ok = True
            for ck, cv in criteria.items():
                if v.get(ck) != cv:
                    ok = False
                    break
            if ok:
                results[k] = v

        return results

    # ------------------------------------------------------
    # DOMAIN HELPERS
    # ------------------------------------------------------
    def lab_core_models(self):
        return self.filter(is_lab_core=True)

    def user_bound_models(self):
        return self.filter(is_user_bound=True)

    def plant_bound_models(self):
        return self.filter(is_plant_bound=True)


# ==========================================================
# GLOBAL INSTANCE
# ==========================================================

laboratory_registry = LaboratoryRegistry()


# ==========================================================
# BOOTSTRAP
# ==========================================================

def bootstrap_laboratory_registry():
    """
    Call inside AppConfig.ready()
    """

    try:
        Laboratory = get_model("Laboratory")

        laboratory_registry.register(
            Laboratory,
            is_lab_core=True,
            is_plant_bound=True,
            is_user_bound=True,
            hooks={
                "get_users": "get_lab_users",
                "get_roles": "get_lab_user_roles",
            }
        )

        logger.info("[laboratory.registry] Bootstrap completed successfully")

    except Exception as e:
        logger.error(f"[laboratory.registry] Bootstrap failed: {e}")


# ==========================================================
# SHORTCUTS
# ==========================================================

def get_lab_core_models():
    return laboratory_registry.lab_core_models()


def get_user_bound_models():
    return laboratory_registry.user_bound_models()


def get_plant_bound_models():
    return laboratory_registry.plant_bound_models()