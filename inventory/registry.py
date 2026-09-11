import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "inventory"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================
def get_model(name: str):
    return apps.get_model(APP_LABEL, name)


# ==========================================================
# MODEL REFERENCES
# ==========================================================
Status = get_model("Status")
Category = get_model("Category")
Supplier = get_model("Supplier")
ItemType = get_model("ItemType")
InventoryItem = get_model("InventoryItem")
StockLedger = get_model("StockLedger")
InventoryTransaction = get_model("InventoryTransaction")
WorkMaterialReservation = get_model("WorkMaterialReservation")
LaboratoryReagent = get_model("LaboratoryReagent")
Equipment = get_model("Equipment")
AlertConfig = get_model("AlertConfig")
AuditLog = get_model("AuditLog")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "Status": "traffic-light",
    "Category": "folder-tree",
    "Supplier": "truck-field",
    "ItemType": "tags",

    "InventoryItem": "boxes-stacked",
    "StockLedger": "warehouse",
    "InventoryTransaction": "right-left",
    "WorkMaterialReservation": "cart-shopping",

    "LaboratoryReagent": "flask",
    "Equipment": "screwdriver-wrench",

    "AlertConfig": "bell",
    "AuditLog": "clock-rotate-left",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "Status": "configuration",
    "Category": "configuration",
    "Supplier": "configuration",
    "ItemType": "configuration",

    "InventoryItem": "inventory",
    "StockLedger": "inventory",
    "InventoryTransaction": "inventory",

    "WorkMaterialReservation": "maintenance",

    "LaboratoryReagent": "laboratory",
    "Equipment": "equipment",

    "AlertConfig": "system",
    "AuditLog": "system",
}


# ==========================================================
# HELPERS
# ==========================================================
def humanize_model_name(model):
    return re.sub(
        r"(?<!^)(?=[A-Z])",
        " ",
        model.__name__,
    ).strip()


def build_meta(model) -> Dict[str, Any]:
    verbose = humanize_model_name(model)

    return {
        "key": f"{model._meta.app_label}.{model._meta.model_name}",
        "app_label": model._meta.app_label,
        "model_name": model._meta.model_name,
        "verbose_name": verbose,
        "verbose_name_plural": f"{verbose}s",
    }


# ==========================================================
# QUERYSET FACTORIES
# ==========================================================
def inventory_qs(model) -> QuerySet:
    return model.objects.select_related(
        "item_type",
        "category",
        "section",
        "supplier",
    ).prefetch_related(
        "transactions",
    )


def transaction_qs(model) -> QuerySet:
    return model.objects.select_related(
        "item",
        "performed_by",
    )


def ledger_qs(model) -> QuerySet:
    return model.objects.select_related(
        "item",
        "item__section",
        "item__category",
    )


def reservation_qs(model) -> QuerySet:
    return model.objects.select_related(
        "inventory_item",
        "inventory_item__category",
        "inventory_item__section",
    )


def reagent_qs(model) -> QuerySet:
    return model.objects.select_related(
        "category",
    )


def equipment_qs(model) -> QuerySet:
    return model.objects.select_related(
        "category",
        "section",
    )


def alert_qs(model) -> QuerySet:
    return model.objects.select_related(
        "section",
        "category",
    ).prefetch_related(
        "users_to_notify",
    )


def audit_qs(model) -> QuerySet:
    return model.objects.select_related(
        "content_type",
        "user",
    )


# ==========================================================
# REGISTRATION WRAPPER
# ==========================================================
def safe_register(model, **kwargs):
    if model is None:
        raise RuntimeError(
            "Model resolution failed."
        )

    meta = kwargs.get("meta", {})
    meta.update(build_meta(model))
    kwargs["meta"] = meta

    ui = kwargs.get("ui", {})
    ui.setdefault(
        "icon",
        ICONS.get(model.__name__, "cube"),
    )
    ui.setdefault(
        "group",
        GROUPS.get(model.__name__, "general"),
    )

    kwargs["ui"] = ui

    try:
        return register_model(**kwargs)(model)
    except Exception:
        logger.exception(
            "[inventory.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# SIMPLE LOOKUP MODELS
# ==========================================================
for model in (
    Status,
    Category,
    Supplier,
    ItemType,
):
    safe_register(
        model,
        search_fields=["name"],
        ordering=["name"],
        inline_edit_fields=["name"],
    )


# ==========================================================
# INVENTORY ITEM
# ==========================================================
safe_register(
    InventoryItem,
    search_fields=[
        "name",
        "category__name",
        "supplier__name",
        "section__name",
    ],
    filter_fields=[
        "item_type",
        "category",
        "section",
        "supplier",
        "is_locked",
    ],
    ordering=[
        "name",
    ],
    queryset_factory=inventory_qs,
    inline_edit_fields=[
        "name",
        "quantity",
        "supplier",
        "expiry_date",
        "is_locked",
    ],
    bulk_actions={
        "reserve_stock": True,
        "issue_stock": True,
        "export": True,
    },
)


# ==========================================================
# STOCK LEDGER
# ==========================================================
safe_register(
    StockLedger,
    search_fields=[
        "item__name",
    ],
    filter_fields=[
        "item__section",
        "item__category",
    ],
    ordering=[
        "item__name",
    ],
    queryset_factory=ledger_qs,
)


# ==========================================================
# TRANSACTIONS
# ==========================================================
safe_register(
    InventoryTransaction,
    search_fields=[
        "item__name",
        "performed_by__username",
    ],
    filter_fields=[
        "transaction_type",
        "performed_by",
    ],
    ordering=[
        "-created_at",
    ],
    queryset_factory=transaction_qs,
    inline_edit_fields=[
        "notes",
    ],
)


# ==========================================================
# RESERVATIONS
# ==========================================================
safe_register(
    WorkMaterialReservation,
    search_fields=[
        "inventory_item__name",
        "work_order_id",
    ],
    filter_fields=[
        "status",
    ],
    ordering=[
        "-created_at",
    ],
    queryset_factory=reservation_qs,
)


# ==========================================================
# REAGENTS
# ==========================================================
safe_register(
    LaboratoryReagent,
    search_fields=[
        "rname",
    ],
    filter_fields=[
        "category",
    ],
    ordering=[
        "rname",
    ],
    queryset_factory=reagent_qs,
    inline_edit_fields=[
        "quantity",
    ],
)


# ==========================================================
# EQUIPMENT
# ==========================================================
safe_register(
    Equipment,
    search_fields=[
        "name",
        "serial_number",
    ],
    filter_fields=[
        "category",
        "section",
    ],
    ordering=[
        "name",
    ],
    queryset_factory=equipment_qs,
    inline_edit_fields=[
        "next_maintenance_date",
        "next_calibration_date",
    ],
)


# ==========================================================
# ALERT CONFIGS
# ==========================================================
safe_register(
    AlertConfig,
    search_fields=[
        "name",
    ],
    filter_fields=[
        "alert_type",
        "active",
        "section",
        "category",
    ],
    ordering=[
        "name",
    ],
    queryset_factory=alert_qs,
    inline_edit_fields=[
        "active",
        "threshold_days",
        "min_quantity",
    ],
)


# ==========================================================
# AUDIT LOGS
# ==========================================================
safe_register(
    AuditLog,
    search_fields=[
        "action",
        "user__username",
        "notes",
    ],
    filter_fields=[
        "action",
        "user",
        "content_type",
    ],
    ordering=[
        "-timestamp",
    ],
    queryset_factory=audit_qs,
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[inventory.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[inventory.registry] registry unavailable during import"
    )