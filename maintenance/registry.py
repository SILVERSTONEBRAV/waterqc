# maintenance/registry.py

import logging
import re
from typing import Any, Dict, Optional, Type

from django.apps import apps
from django.db.models import Model

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "maintenance"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================

def get_model(model_name: str) -> Type[Model]:
    """
    Lazy resolver for maintenance models.
    Prevents circular imports across inventory, duty_house, and maintenance flows.
    """
    try:
        return apps.get_model(APP_LABEL, model_name)
    except Exception as e:
        logger.error(f"[maintenance.registry] Failed to resolve {model_name}: {e}")
        raise


# ==========================================================
# KEY HELPERS
# ==========================================================

def _key(model: Type[Model]) -> str:
    return f"{model._meta.app_label}.{model._meta.model_name}"


def _humanize(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name).strip()


# ==========================================================
# REGISTRY CORE
# ==========================================================

class MaintenanceRegistry:
    """
    Registry for maintenance workflow engine:

    WorkRequest → WorkOrder → WorkTask
    + SLA + Cost + Material usage integration
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

        self._registry[key] = {
            "key": key,
            "app_label": model._meta.app_label,
            "model_name": model._meta.model_name,
            "verbose_name": str(model._meta.verbose_name),
            "verbose_name_plural": str(model._meta.verbose_name_plural),
            "human_name": _humanize(model.__name__),

            # workflow flags
            "is_request": config.get("is_request", False),
            "is_order": config.get("is_order", False),
            "is_task": config.get("is_task", False),

            # engine capabilities
            "is_sla_tracked": config.get("is_sla_tracked", False),
            "is_costed": config.get("is_costed", False),
            "is_material_aware": config.get("is_material_aware", False),

            # lifecycle hooks (string-based for decoupling)
            "hooks": config.get("hooks", {}),
        }

        logger.info(f"[maintenance.registry] Registered {key}")

        # sync to global registry if present
        try:
            register_model(model, **self._registry[key])
        except Exception as e:
            logger.warning(f"[maintenance.registry] global sync failed for {key}: {e}")

    # ------------------------------------------------------
    # GET
    # ------------------------------------------------------
    def get(self, model: Type[Model]) -> Optional[Dict[str, Any]]:
        return self._registry.get(_key(model))

    # ------------------------------------------------------
    # QUERY
    # ------------------------------------------------------
    def all(self) -> Dict[str, Dict[str, Any]]:
        return self._registry

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
    # DOMAIN GROUPS
    # ------------------------------------------------------
    def request_models(self):
        return self.filter(is_request=True)

    def order_models(self):
        return self.filter(is_order=True)

    def task_models(self):
        return self.filter(is_task=True)

    def sla_models(self):
        return self.filter(is_sla_tracked=True)

    def cost_models(self):
        return self.filter(is_costed=True)

    def material_models(self):
        return self.filter(is_material_aware=True)


# ==========================================================
# GLOBAL INSTANCE
# ==========================================================

maintenance_registry = MaintenanceRegistry()


# ==========================================================
# BOOTSTRAP REGISTRATION
# ==========================================================

def bootstrap_maintenance_registry():
    """
    Call in AppConfig.ready()
    """

    try:
        WorkRequest = get_model("WorkRequest")
        WorkOrder = get_model("WorkOrder")
        WorkTask = get_model("WorkTask")
        WorkMaterialUsage = get_model("WorkMaterialUsage")
        WorkCost = get_model("WorkCost")
        SLARecord = get_model("SLARecord")

        # -------------------------
        # CORE WORKFLOW
        # -------------------------
        maintenance_registry.register(
            WorkRequest,
            is_request=True,
            is_sla_tracked=True,
            hooks={
                "approve": "approve",
                "convert": "convert_to_order",
            }
        )

        maintenance_registry.register(
            WorkOrder,
            is_order=True,
            is_costed=True,
            is_material_aware=True,
            hooks={
                "assign": "assign",
                "start": "start",
                "complete": "complete",
            }
        )

        maintenance_registry.register(
            WorkTask,
            is_task=True,
            hooks={
                "start": "start",
                "complete": "complete",
            }
        )

        # -------------------------
        # SUPPORT SYSTEMS
        # -------------------------
        maintenance_registry.register(
            WorkMaterialUsage,
            is_material_aware=True
        )

        maintenance_registry.register(
            WorkCost,
            is_costed=True
        )

        maintenance_registry.register(
            SLARecord,
            is_sla_tracked=True
        )

        logger.info("[maintenance.registry] Bootstrap completed successfully")

    except Exception as e:
        logger.error(f"[maintenance.registry] Bootstrap failed: {e}")


# ==========================================================
# SHORTCUT HELPERS
# ==========================================================

def get_request_models():
    return maintenance_registry.request_models()


def get_order_models():
    return maintenance_registry.order_models()


def get_task_models():
    return maintenance_registry.task_models()


def get_sla_models():
    return maintenance_registry.sla_models()


def get_cost_models():
    return maintenance_registry.cost_models()


def get_material_models():
    return maintenance_registry.material_models()