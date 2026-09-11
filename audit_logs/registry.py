# audit_logs/registry.py

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Callable, Optional, List

from django.apps import apps

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "audit_logs"


# ==========================================================
# SAFE LAZY MODEL RESOLUTION
# ==========================================================
def get_model(name: str):
    """
    Lazy resolution ONLY at runtime or bootstrap.
    Prevents import-time coupling.
    """
    return apps.get_model(APP_LABEL, name)


# ==========================================================
# DOMAIN LAYERS (AUDIT SYSTEM SEGMENTATION)
# ==========================================================
DOMAIN_LAYERS = {
    "AuditLogEntry": "core",
    "UserActivity": "telemetry",
    "AuditEventStream": "streaming",
}


# ==========================================================
# ICON SYSTEM (UI METADATA)
# ==========================================================
ICONS = {
    "AuditLogEntry": "shield-halved",
    "UserActivity": "user-clock",
    "AuditEventStream": "wave-square",
}


# ==========================================================
# AUDIT PRIORITY / STATUS INTELLIGENCE
# ==========================================================
STATUS_FILTERS = {
    "AuditLogEntry": ["result_status", "priority"],
    "UserActivity": ["activity_type", "successful_attempt"],
}


# ==========================================================
# QUERYSET STRATEGY ENGINE (HIGH VOLUME OPTIMIZATION)
# ==========================================================
def auditlog_qs(model):
    return model.objects.select_related("user").only(
        "id",
        "user",
        "action",
        "result_status",
        "timestamp",
        "ip_address",
        "device",
        "path",
        "priority",
    )


def activity_qs(model):
    return model.objects.select_related(
        "user",
        "audit_entry",
        "audit_entry__user",
    ).only(
        "id",
        "user",
        "audit_entry",
        "activity_type",
        "successful_attempt",
        "timestamp",
        "duration",
    )


# ==========================================================
# REGISTRY ENTRY STRUCTURE
# ==========================================================
@dataclass
class AuditRegistryEntry:
    model: Any
    group: str
    icon: str

    search_fields: List[str] = field(default_factory=list)
    filter_fields: List[str] = field(default_factory=list)
    ordering: List[str] = field(default_factory=list)

    inline_edit_fields: List[str] = field(default_factory=list)
    select_related: List[str] = field(default_factory=list)

    queryset_factory: Optional[Callable] = None

    bulk_actions: Dict[str, bool] = field(default_factory=dict)
    permissions: Dict[str, List[str]] = field(default_factory=dict)

    meta: Dict[str, Any] = field(default_factory=dict)


# ==========================================================
# CENTRAL REGISTRY STORE
# ==========================================================
REGISTRY: Dict[str, AuditRegistryEntry] = {}


# ==========================================================
# META BUILDER (UI + API INTROSPECTION)
# ==========================================================
def build_meta(model) -> Dict[str, Any]:
    name = model.__name__
    verbose = re.sub(r"(?<!^)(?=[A-Z])", " ", name)

    return {
        "app_label": model._meta.app_label,
        "model_name": model._meta.model_name,
        "verbose_name": verbose,
        "verbose_name_plural": f"{verbose}s",
        "key": f"{model._meta.app_label}.{model._meta.model_name}",
        "is_audit_model": True,
    }


# ==========================================================
# SAFE REGISTRATION ENGINE
# ==========================================================
def safe_register(
    model,
    *,
    search_fields=None,
    filter_fields=None,
    ordering=None,
    inline_edit_fields=None,
    select_related=None,
    queryset_factory=None,
    bulk_actions=None,
    permissions=None,
):
    if model is None:
        raise RuntimeError("[audit_logs.registry] model resolution failed")

    name = model.__name__

    entry = AuditRegistryEntry(
        model=model,
        group=DOMAIN_LAYERS.get(name, "core"),
        icon=ICONS.get(name, "shield-halved"),

        search_fields=search_fields or [],
        filter_fields=filter_fields or [],
        ordering=ordering or ["-timestamp"],
        inline_edit_fields=inline_edit_fields or [],
        select_related=select_related or [],

        queryset_factory=queryset_factory,
        bulk_actions=bulk_actions or {},
        permissions=permissions or {},

        meta=build_meta(model),
    )

    REGISTRY[name] = entry

    try:
        return register_model(
            search_fields=entry.search_fields,
            filter_fields=entry.filter_fields,
            ordering=entry.ordering,
            inline_edit_fields=entry.inline_edit_fields,
            select_related=entry.select_related,
            queryset_factory=entry.queryset_factory,
            bulk_actions=entry.bulk_actions,
            meta=entry.meta,
            ui={
                "icon": entry.icon,
                "group": entry.group,
            },
        )(model)

    except Exception:
        logger.exception("[audit_logs.registry] failed registering %s", name)
        raise


# ==========================================================
# BOOTSTRAP (CALL IN apps.py READY())
# ==========================================================
def bootstrap_registry():
    """
    Central initialization entrypoint.
    """

    safe_register(
        get_model("AuditLogEntry"),
        search_fields=[
            "action",
            "user__username",
            "ip_address",
            "path",
        ],
        filter_fields=[
            "result_status",
            "priority",
            "device",
        ],
        ordering=["-timestamp"],
        inline_edit_fields=[
            "result_status",
            "priority",
        ],
        queryset_factory=auditlog_qs,
        bulk_actions={
            "mark_high_priority": True,
            "mark_resolved": True,
        },
        permissions={
            "mark_high_priority": ["Admin", "Security Officer"],
        },
    )

    safe_register(
        get_model("UserActivity"),
        search_fields=[
            "user__username",
            "activity_type",
            "audit_entry__action",
        ],
        filter_fields=[
            "activity_type",
            "successful_attempt",
        ],
        ordering=["-timestamp"],
        inline_edit_fields=[
            "successful_attempt",
        ],
        queryset_factory=activity_qs,
        bulk_actions={
            "flag_anomaly": True,
        },
        permissions={
            "flag_anomaly": ["Admin", "Security Officer"],
        },
    )

    logger.info(
        "[audit_logs.registry] bootstrap complete (%s models)",
        len(REGISTRY),
    )


# ==========================================================
# INTROSPECTION API (DASHBOARD / ADMIN / ANALYTICS)
# ==========================================================
def get_registry():
    return REGISTRY


def get_model_entry(name: str):
    return REGISTRY.get(name)


def list_by_group(group: str):
    return [e for e in REGISTRY.values() if e.group == group]


def list_bulk_actions(model_name: str):
    entry = REGISTRY.get(model_name)
    return entry.bulk_actions if entry else {}