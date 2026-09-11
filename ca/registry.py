# ca/registry.py

import logging
import re
from copy import deepcopy
from typing import Any, Dict

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "ca"


def get_model(name: str):
    return apps.get_model(APP_LABEL, name)


Chemical = get_model("Chemical")
Supplier = get_model("Supplier")
ChemicalLocation = get_model("ChemicalLocation")
ChemicalSpecification = get_model("ChemicalSpecification")

ChemicalBatch = get_model("ChemicalBatch")
ChemicalAnalysisRequest = get_model("ChemicalAnalysisRequest")
BatchTestResult = get_model("BatchTestResult")
ChemicalAnalysisInput = get_model("ChemicalAnalysisInput")

ChemicalCoA = get_model("ChemicalCoA")

PackagingStatus = get_model("PackagingStatus")
ChemicalCertApprover = get_model("ChemicalCertApprover")
ChecklistForWaterTreatmentChemicalAnalysis = get_model(
    "ChecklistForWaterTreatmentChemicalAnalysis"
)


ICONS = {
    "Chemical": "flask",
    "Supplier": "truck",
    "ChemicalLocation": "location-dot",
    "ChemicalSpecification": "vial-circle-check",
    "ChemicalBatch": "boxes-stacked",
    "ChemicalAnalysisRequest": "clipboard-list",
    "BatchTestResult": "microscope",
    "ChemicalAnalysisInput": "keyboard",
    "ChemicalCoA": "certificate",
    "PackagingStatus": "box",
    "ChemicalCertApprover": "signature",
    "ChecklistForWaterTreatmentChemicalAnalysis": "clipboard-check",
}


GROUPS = {
    "Chemical": "chemicals",
    "Supplier": "suppliers",
    "ChemicalLocation": "inventory",
    "ChemicalSpecification": "specifications",
    "ChemicalBatch": "batches",
    "ChemicalAnalysisRequest": "analysis",
    "BatchTestResult": "results",
    "ChemicalAnalysisInput": "analysis",
    "ChemicalCoA": "certificates",
    "PackagingStatus": "logistics",
    "ChemicalCertApprover": "compliance",
    "ChecklistForWaterTreatmentChemicalAnalysis": "compliance",
}


def humanize_model_name(model) -> str:
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


def chemical_qs(model) -> QuerySet:
    return model.objects.prefetch_related(
        "specifications",
    )


def supplier_qs(model) -> QuerySet:
    return model.objects.all()


def location_qs(model) -> QuerySet:
    return model.objects.select_related(
        "treatment_plant",
    )


def specification_qs(model) -> QuerySet:
    return model.objects.select_related(
        "chemical",
        "method",
    )


def batch_qs(model) -> QuerySet:
    return model.objects.select_related(
        "chemical",
        "supplier",
        "treatment_plant",
        "received_by",
    ).prefetch_related(
        "test_results",
        "test_results__parameter",
    )


def request_qs(model) -> QuerySet:
    return model.objects.select_related(
        "batch",
        "requested_by",
        "received_by",
        "location",
    ).prefetch_related(
        "assigned_analysts",
    )


def result_qs(model) -> QuerySet:
    return model.objects.select_related(
        "batch",
        "parameter",
        "parameter__chemical",
        "analyst",
    )


def input_qs(model) -> QuerySet:
    return model.objects.select_related(
        "test_result",
        "test_result__batch",
        "test_result__parameter",
    )


def coa_qs(model) -> QuerySet:
    return model.objects.select_related(
        "batch",
        "approved_by",
        "packaging_status",
    )


def approver_qs(model) -> QuerySet:
    return model.objects.select_related(
        "user",
    )


def checklist_qs(model) -> QuerySet:
    return model.objects.select_related(
        "chemical_analysis_request",
        "chemical",
        "sampled_by",
        "requested_by",
    )


LOOKUP_BASE_CONFIG = {
    "ordering": [
        "name",
    ],
}


BATCH_BASE_CONFIG = {
    "search_fields": [
        "sample_id",
        "batch_number",
        "chemical__name",
        "supplier__name",
    ],
    "filter_fields": [
        "status",
        "chemical",
        "supplier",
        "treatment_plant",
    ],
    "ordering": [
        "-received_date",
    ],
    "select_related": [
        "chemical",
        "supplier",
        "treatment_plant",
        "received_by",
    ],
    "queryset_factory": batch_qs,
}


ANALYSIS_REQUEST_BASE_CONFIG = {
    "search_fields": [
        "request_id",
        "batch__sample_id",
        "batch__batch_number",
    ],
    "filter_fields": [
        "status",
        "batch",
        "location",
    ],
    "ordering": [
        "-created_at",
    ],
    "select_related": [
        "batch",
        "requested_by",
        "received_by",
        "location",
    ],
    "queryset_factory": request_qs,
}


TEST_RESULT_BASE_CONFIG = {
    "search_fields": [
        "batch__sample_id",
        "batch__batch_number",
        "parameter__parameter_name",
        "parameter__chemical__name",
    ],
    "filter_fields": [
        "status",
        "batch",
        "parameter",
        "analyst",
    ],
    "ordering": [
        "-tested_at",
    ],
    "select_related": [
        "batch",
        "parameter",
        "parameter__chemical",
        "analyst",
    ],
    "queryset_factory": result_qs,
}


CERTIFICATE_BASE_CONFIG = {
    "search_fields": [
        "batch__sample_id",
        "batch__batch_number",
        "chemical_name",
    ],
    "filter_fields": [
        "packaging_status",
        "batch",
        "approved_by",
    ],
    "ordering": [
        "-date_of_report",
    ],
    "select_related": [
        "batch",
        "approved_by",
        "packaging_status",
    ],
    "queryset_factory": coa_qs,
}


CHECKLIST_BASE_CONFIG = {
    "search_fields": [
        "chemical__name",
        "chemical_analysis_request__request_id",
    ],
    "filter_fields": [
        "grade",
        "country_of_origin",
        "chemical",
        "chemical_analysis_request",
    ],
    "ordering": [
        "-created_at",
    ],
    "select_related": [
        "chemical_analysis_request",
        "chemical",
        "sampled_by",
        "requested_by",
    ],
    "queryset_factory": checklist_qs,
}


MODEL_CAPABILITIES = {
    "Chemical": {
        "create": True,
        "update": True,
        "delete": True,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
    },
    "Supplier": {
        "create": True,
        "update": True,
        "delete": True,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
    },
    "ChemicalLocation": {
        "create": True,
        "update": True,
        "delete": True,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
    },
    "ChemicalSpecification": {
        "create": True,
        "update": True,
        "delete": True,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
    },
    "ChemicalBatch": {
        "create": True,
        "update": True,
        "delete": False,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
        "workflow": True,
    },
    "ChemicalAnalysisRequest": {
        "create": True,
        "update": True,
        "delete": False,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
        "workflow": True,
    },
    "BatchTestResult": {
        "create": True,
        "update": True,
        "delete": False,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
        "workflow": True,
    },
    "ChemicalAnalysisInput": {
        "create": True,
        "update": True,
        "delete": False,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
    },
    "ChemicalCoA": {
        "create": False,
        "update": False,
        "delete": False,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": False,
        "workflow": True,
        "document": True,
    },
    "PackagingStatus": {
        "create": True,
        "update": True,
        "delete": True,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
    },
    "ChemicalCertApprover": {
        "create": True,
        "update": True,
        "delete": True,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
    },
    "ChecklistForWaterTreatmentChemicalAnalysis": {
        "create": True,
        "update": True,
        "delete": False,
        "search": True,
        "filter": True,
        "export": True,
        "bulk_edit": True,
    },
}


PERMISSIONS = {
    "Chemical": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
        ],
        "update": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
        ],
        "delete": [
            "Lab Supervisor",
            "QA Officer",
        ],
    },
    "Supplier": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "Lab Supervisor",
            "QA Officer",
        ],
        "update": [
            "Lab Supervisor",
            "QA Officer",
        ],
        "delete": [
            "Lab Supervisor",
        ],
    },
    "ChemicalLocation": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "Lab Supervisor",
        ],
        "update": [
            "Lab Supervisor",
        ],
        "delete": [
            "Lab Supervisor",
        ],
    },
    "ChemicalSpecification": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "Lab Supervisor",
            "QA Officer",
        ],
        "update": [
            "Lab Supervisor",
            "QA Officer",
        ],
        "delete": [
            "QA Officer",
        ],
    },
    "ChemicalBatch": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
        ],
        "update": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
        ],
        "approve": [
            "Lab Supervisor",
            "QA Officer",
        ],
        "reject": [
            "Lab Supervisor",
            "QA Officer",
        ],
        "utilize": [
            "Operations",
            "Lab Supervisor",
        ],
    },
    "ChemicalAnalysisRequest": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
        ],
        "update": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
        ],
        "start_analysis": [
            "Lab Technician",
            "Lab Assistant",
        ],
        "complete_analysis": [
            "Lab Supervisor",
        ],
        "cancel": [
            "Lab Supervisor",
            "QA Officer",
        ],
    },
    "BatchTestResult": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "Lab Technician",
            "Lab Assistant",
        ],
        "update": [
            "Lab Technician",
            "Lab Assistant",
        ],
        "verify": [
            "Lab Supervisor",
        ],
        "reject": [
            "Lab Supervisor",
            "QA Officer",
        ],
    },
    "ChemicalAnalysisInput": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "Lab Technician",
            "Lab Assistant",
        ],
        "update": [
            "Lab Technician",
            "Lab Assistant",
        ],
    },
    "ChemicalCoA": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "generate": [
            "Lab Supervisor",
            "QA Officer",
        ],
        "verify": [
            "QA Officer",
        ],
        "approve": [
            "ChemicalCertApprover",
            "QA Officer",
        ],
        "download": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
    },
    "PackagingStatus": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "Lab Supervisor",
        ],
        "update": [
            "Lab Supervisor",
        ],
        "delete": [
            "Lab Supervisor",
        ],
    },
    "ChemicalCertApprover": {
        "view": [
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "QA Officer",
        ],
        "update": [
            "QA Officer",
        ],
        "delete": [
            "QA Officer",
        ],
    },
    "ChecklistForWaterTreatmentChemicalAnalysis": {
        "view": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
            "QA Officer",
        ],
        "create": [
            "Lab Technician",
            "Lab Assistant",
        ],
        "update": [
            "Lab Technician",
            "Lab Assistant",
            "Lab Supervisor",
        ],
        "verify": [
            "Lab Supervisor",
            "QA Officer",
        ],
    },
}


WORKFLOW_CONFIG = {
    "ChemicalBatch": {
        "enabled": True,
        "states": [
            "received",
            "under_analysis",
            "approved",
            "rejected",
            "utilized",
        ],
        "transitions": {
            "received": [
                "under_analysis",
                "rejected",
            ],
            "under_analysis": [
                "approved",
                "rejected",
            ],
            "approved": [
                "utilized",
            ],
            "rejected": [],
            "utilized": [],
        },
        "actions": [
            "approve",
            "reject",
            "utilize",
        ],
    },
    "ChemicalAnalysisRequest": {
        "enabled": True,
        "states": [
            "pending",
            "assigned",
            "in_progress",
            "completed",
            "rejected",
            "cancelled",
        ],
        "transitions": {
            "pending": [
                "assigned",
                "cancelled",
            ],
            "assigned": [
                "in_progress",
                "cancelled",
            ],
            "in_progress": [
                "completed",
                "rejected",
            ],
            "completed": [],
            "rejected": [],
            "cancelled": [],
        },
        "actions": [
            "start_analysis",
            "complete_analysis",
            "cancel",
        ],
    },
    "BatchTestResult": {
        "enabled": True,
        "states": [
            "pending",
            "analysed",
            "verified",
            "rejected",
        ],
        "transitions": {
            "pending": [
                "analysed",
            ],
            "analysed": [
                "verified",
                "rejected",
            ],
            "verified": [],
            "rejected": [],
        },
        "actions": [
            "verify",
            "reject",
        ],
    },
    "ChemicalCoA": {
        "enabled": True,
        "states": [
            "draft",
            "generated",
            "verified",
            "approved",
            "revoked",
        ],
        "transitions": {
            "draft": [
                "generated",
            ],
            "generated": [
                "verified",
                "revoked",
            ],
            "verified": [
                "approved",
                "revoked",
            ],
            "approved": [
                "revoked",
            ],
            "revoked": [],
        },
        "actions": [
            "generate",
            "verify",
            "approve",
            "download",
        ],
    },
}


AUDIT_CONFIG = {
    "Chemical": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": True,
    },
    "Supplier": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": True,
    },
    "ChemicalLocation": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": True,
    },
    "ChemicalSpecification": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": True,
    },
    "ChemicalBatch": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": False,
        "track_workflow": True,
    },
    "ChemicalAnalysisRequest": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": False,
        "track_workflow": True,
    },
    "BatchTestResult": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": False,
        "track_workflow": True,
    },
    "ChemicalAnalysisInput": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": False,
    },
    "ChemicalCoA": {
        "enabled": True,
        "track_create": True,
        "track_update": False,
        "track_delete": False,
        "track_workflow": True,
        "track_download": True,
    },
    "PackagingStatus": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": True,
    },
    "ChemicalCertApprover": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": True,
    },
    "ChecklistForWaterTreatmentChemicalAnalysis": {
        "enabled": True,
        "track_create": True,
        "track_update": True,
        "track_delete": False,
    },
}


EXPORT_CONFIG = {
    "Chemical": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "name",
            "code",
            "grade",
        ],
    },
    "Supplier": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "name",
            "code",
            "contact_person",
            "phone",
            "email",
        ],
    },
    "ChemicalLocation": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "name",
            "code",
            "treatment_plant",
            "status",
        ],
    },
    "ChemicalSpecification": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "chemical",
            "parameter_name",
            "minimum_value",
            "maximum_value",
            "method",
            "status",
        ],
    },
    "ChemicalBatch": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "sample_id",
            "batch_number",
            "chemical",
            "supplier",
            "treatment_plant",
            "status",
            "quantity_received",
            "received_date",
        ],
    },
    "ChemicalAnalysisRequest": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "request_id",
            "batch",
            "status",
            "created_at",
            "analysis_deadline",
        ],
    },
    "BatchTestResult": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "batch",
            "parameter",
            "value",
            "status",
            "tested_at",
            "analyst",
        ],
    },
    "ChemicalAnalysisInput": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "test_result",
            "value",
            "remarks",
        ],
    },
    "ChemicalCoA": {
        "formats": [
            "pdf",
        ],
        "columns": [
            "batch",
            "chemical_name",
            "date_of_report",
            "packaging_status",
            "approved_by",
        ],
    },
    "PackagingStatus": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "name",
            "code",
            "status",
        ],
    },
    "ChemicalCertApprover": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "user",
            "status",
        ],
    },
    "ChecklistForWaterTreatmentChemicalAnalysis": {
        "formats": [
            "csv",
            "xlsx",
            "pdf",
        ],
        "columns": [
            "chemical",
            "chemical_analysis_request",
            "grade",
            "country_of_origin",
            "created_at",
        ],
    },
}


def get_model_field_names(model):
    names = set()

    for field in model._meta.get_fields():
        if getattr(field, "concrete", False):
            names.add(field.name)

    return names


def valid_fields(model, fields):
    available = get_model_field_names(model)
    result = []

    for field_name in fields or []:
        root = field_name.lstrip("-").split("__")[0]

        if root in available:
            result.append(field_name)

    return result


def validate_registry_fields(model, config):
    field_configs = (
        "search_fields",
        "filter_fields",
        "ordering",
        "inline_edit_fields",
        "select_related",
        "prefetch_related",
    )

    for key in field_configs:
        values = config.get(key, [])

        if not values:
            continue

        invalid = []

        for value in values:
            root = value.lstrip("-").split("__")[0]

            try:
                model._meta.get_field(root)
            except FieldDoesNotExist:
                invalid.append(value)

        if invalid:
            logger.warning(
                "[ca.registry] %s contains invalid %s: %s",
                model.__name__,
                key,
                invalid,
            )


def build_model_config(model, **kwargs):
    name = model.__name__

    config = deepcopy(kwargs)

    config.setdefault(
        "capabilities",
        deepcopy(
            MODEL_CAPABILITIES.get(
                name,
                {},
            )
        ),
    )

    config.setdefault(
        "permissions",
        deepcopy(
            PERMISSIONS.get(
                name,
                {},
            )
        ),
    )

    config.setdefault(
        "workflow",
        deepcopy(
            WORKFLOW_CONFIG.get(
                name,
                {},
            )
        ),
    )

    config.setdefault(
        "audit",
        deepcopy(
            AUDIT_CONFIG.get(
                name,
                {},
            )
        ),
    )

    config.setdefault(
        "export",
        deepcopy(
            EXPORT_CONFIG.get(
                name,
                {},
            )
        ),
    )

    validate_registry_fields(
        model,
        config,
    )

    return config


def safe_register(model, **kwargs):
    if model is None:
        raise RuntimeError(
            "[ca.registry] Model resolution failed."
        )

    config = build_model_config(
        model,
        **kwargs,
    )

    meta = config.get(
        "meta",
        {},
    ).copy()

    meta.update(
        build_meta(model)
    )

    config["meta"] = meta

    ui = config.get(
        "ui",
        {},
    ).copy()

    ui.setdefault(
        "icon",
        ICONS.get(
            model.__name__,
            "flask",
        ),
    )

    ui.setdefault(
        "group",
        GROUPS.get(
            model.__name__,
            "general",
        ),
    )

    config["ui"] = ui

    config.pop(
        "templates",
        None,
    )

    try:
        return register_model(
            **config
        )(model)

    except Exception:
        logger.exception(
            "[ca.registry] Failed registering %s",
            model,
        )
        raise


safe_register(
    Chemical,
    search_fields=[
        "name",
        "code",
    ],
    filter_fields=[
        "grade",
        "status",
    ],
    ordering=[
        "name",
    ],
    prefetch_related=[
        "specifications",
    ],
    queryset_factory=chemical_qs,
    inline_edit_fields=[
        "name",
        "code",
        "grade",
    ],
)


safe_register(
    Supplier,
    search_fields=[
        "name",
        "code",
        "contact_person",
    ],
    filter_fields=[
        "status",
    ],
    ordering=[
        "name",
    ],
    queryset_factory=supplier_qs,
    inline_edit_fields=[
        "name",
        "code",
        "contact_person",
        "phone",
        "email",
    ],
)


safe_register(
    ChemicalLocation,
    search_fields=[
        "name",
        "code",
    ],
    filter_fields=[
        "treatment_plant",
        "status",
    ],
    ordering=[
        "name",
    ],
    select_related=[
        "treatment_plant",
    ],
    queryset_factory=location_qs,
    inline_edit_fields=[
        "name",
        "code",
        "status",
    ],
)


safe_register(
    ChemicalSpecification,
    search_fields=[
        "chemical__name",
        "chemical__code",
        "parameter_name",
    ],
    filter_fields=[
        "chemical",
        "method",
        "status",
    ],
    ordering=[
        "chemical__name",
        "parameter_name",
    ],
    select_related=[
        "chemical",
        "method",
    ],
    queryset_factory=specification_qs,
    inline_edit_fields=[
        "parameter_name",
        "minimum_value",
        "maximum_value",
        "method",
    ],
)


safe_register(
    ChemicalBatch,
    **BATCH_BASE_CONFIG,
    inline_edit_fields=[
        "status",
        "remarks",
        "quantity_received",
        "received_date",
    ],
    bulk_actions={
        "approve": True,
        "reject": True,
        "utilize": True,
    },
)


safe_register(
    ChemicalAnalysisRequest,
    **ANALYSIS_REQUEST_BASE_CONFIG,
    inline_edit_fields=[
        "status",
        "analysis_deadline",
    ],
    bulk_actions={
        "start_analysis": True,
        "complete_analysis": True,
    },
)


safe_register(
    BatchTestResult,
    **TEST_RESULT_BASE_CONFIG,
    inline_edit_fields=[
        "value",
        "status",
        "textual_result",
    ],
    bulk_actions={
        "verify": True,
        "reject": True,
    },
)


safe_register(
    ChemicalAnalysisInput,
    search_fields=[
        "test_result__id",
        "test_result__batch__sample_id",
        "test_result__parameter__parameter_name",
    ],
    filter_fields=[
        "test_result",
    ],
    ordering=[
        "-id",
    ],
    select_related=[
        "test_result",
        "test_result__batch",
        "test_result__parameter",
    ],
    queryset_factory=input_qs,
    inline_edit_fields=[
        "value",
        "remarks",
    ],
)


safe_register(
    ChemicalCoA,
    **CERTIFICATE_BASE_CONFIG,
    bulk_actions={
        "generate": True,
        "verify": True,
        "approve": True,
        "download": True,
    },
    meta={
        "document_type": "certificate_of_analysis",
        "supports_pdf": True,
        "supports_hash_verification": True,
    },
)


safe_register(
    PackagingStatus,
    search_fields=[
        "name",
        "code",
    ],
    filter_fields=[
        "status",
    ],
    ordering=[
        "name",
    ],
    inline_edit_fields=[
        "name",
        "code",
        "status",
    ],
)


safe_register(
    ChemicalCertApprover,
    search_fields=[
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    ],
    filter_fields=[
        "user",
        "status",
    ],
    ordering=[
        "user__username",
    ],
    select_related=[
        "user",
    ],
    queryset_factory=approver_qs,
    inline_edit_fields=[
        "status",
    ],
)


safe_register(
    ChecklistForWaterTreatmentChemicalAnalysis,
    **CHECKLIST_BASE_CONFIG,
)


try:
    from core.registry import registry

    logger.info(
        "[ca.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[ca.registry] registry unavailable during import"
    )


def get_capabilities(model_name: str):
    return deepcopy(
        MODEL_CAPABILITIES.get(
            model_name,
            {},
        )
    )


def get_permissions(model_name: str):
    return deepcopy(
        PERMISSIONS.get(
            model_name,
            {},
        )
    )


def get_workflow(model_name: str):
    return deepcopy(
        WORKFLOW_CONFIG.get(
            model_name,
            {},
        )
    )


def get_audit_config(model_name: str):
    return deepcopy(
        AUDIT_CONFIG.get(
            model_name,
            {},
        )
    )


def get_export_config(model_name: str):
    return deepcopy(
        EXPORT_CONFIG.get(
            model_name,
            {},
        )
    )


def get_registered_models():
    try:
        from core.registry import registry

        return dict(
            registry._registry
        )

    except Exception:
        return {}


def is_registered(model_name: str) -> bool:
    try:
        from core.registry import registry

        return model_name in registry._registry

    except Exception:
        return False


def get_registered_model(model_name: str):
    try:
        from core.registry import registry

        return registry._registry.get(
            model_name
        )

    except Exception:
        return None


def list_registered_models():
    return sorted(
        get_registered_models().keys()
    )


def registry_health() -> Dict[str, Any]:
    registered = get_registered_models()

    expected_models = {
        "Chemical": Chemical,
        "Supplier": Supplier,
        "ChemicalLocation": ChemicalLocation,
        "ChemicalSpecification": ChemicalSpecification,
        "ChemicalBatch": ChemicalBatch,
        "ChemicalAnalysisRequest": ChemicalAnalysisRequest,
        "BatchTestResult": BatchTestResult,
        "ChemicalAnalysisInput": ChemicalAnalysisInput,
        "ChemicalCoA": ChemicalCoA,
        "PackagingStatus": PackagingStatus,
        "ChemicalCertApprover": ChemicalCertApprover,
        "ChecklistForWaterTreatmentChemicalAnalysis": (
            ChecklistForWaterTreatmentChemicalAnalysis
        ),
    }

    expected = {
        name
        for name, model in expected_models.items()
        if model is not None
    }

    actual = set(
        registered.keys()
    )

    missing = sorted(
        expected - actual
    )

    unexpected = sorted(
        actual - expected
    )

    return {
        "app_label": APP_LABEL,
        "expected_models": len(expected),
        "registered_models": len(actual),
        "missing": missing,
        "unexpected": unexpected,
        "healthy": not missing and not unexpected,
    }


def registry_summary() -> Dict[str, Any]:
    registered = get_registered_models()

    summary = {
        "app_label": APP_LABEL,
        "models": [],
        "groups": {},
        "workflow_models": [],
        "document_models": [],
        "exportable_models": [],
    }

    for model_name in sorted(registered):
        capabilities = get_capabilities(
            model_name
        )

        workflow = get_workflow(
            model_name
        )

        meta = {}

        registered_entry = registered.get(
            model_name
        )

        if hasattr(
            registered_entry,
            "meta",
        ):
            meta = getattr(
                registered_entry,
                "meta",
                {},
            )

        elif isinstance(
            registered_entry,
            dict,
        ):
            meta = registered_entry.get(
                "meta",
                {},
            )

        group = GROUPS.get(
            model_name,
            "general",
        )

        summary["models"].append(
            {
                "name": model_name,
                "key": meta.get(
                    "key",
                    f"{APP_LABEL}.{model_name.lower()}",
                ),
                "group": group,
                "capabilities": deepcopy(
                    capabilities
                ),
            }
        )

        summary["groups"].setdefault(
            group,
            [],
        ).append(
            model_name
        )

        if workflow.get(
            "enabled",
            False,
        ):
            summary["workflow_models"].append(
                model_name
            )

        if capabilities.get(
            "document",
            False,
        ):
            summary["document_models"].append(
                model_name
            )

        if capabilities.get(
            "export",
            False,
        ):
            summary["exportable_models"].append(
                model_name
            )

    summary["model_count"] = len(
        summary["models"]
    )

    summary["workflow_count"] = len(
        summary["workflow_models"]
    )

    summary["document_count"] = len(
        summary["document_models"]
    )

    summary["exportable_count"] = len(
        summary["exportable_models"]
    )

    return summary