import logging
import re
from typing import Any, Dict

from django.apps import apps
from django.db.models import QuerySet

from core.registry import register_model

logger = logging.getLogger(__name__)

APP_LABEL = "wc"


# ==========================================================
# SAFE MODEL RESOLUTION
# ==========================================================
def get_model(name: str):
    """
    Lazy model resolver.
    Prevents circular imports during app loading.
    """
    return apps.get_model(APP_LABEL, name)


# ==========================================================
# MODEL REFERENCES
# ==========================================================
WaterQualityComplaint = get_model("WaterQualityComplaint")
WaterQualityComplaintCategory = get_model("WaterQualityComplaintCategory")
SampleCondition = get_model("SampleCondition")

ComplaintPost = get_model("ComplaintPost")
ComplaintResolution = get_model("ComplaintResolution")
ComplaintAttachment = get_model("ComplaintAttachment")
ComplaintStatusLog = get_model("ComplaintStatusLog")

WaterSample = get_model("WaterSample")
WaterSampleParameterResult = get_model("WaterSampleParameterResult")

ComplaintMicrobialAnalysis = get_model("ComplaintMicrobialAnalysis")
ComplaintMicrobialParameterResult = get_model("ComplaintMicrobialParameterResult")

ComplaintConfirmationReport = get_model("ComplaintConfirmationReport")
ComplaintAuditTrail = get_model("ComplaintAuditTrail")


# ==========================================================
# ICON MAP
# ==========================================================
ICONS = {
    "WaterQualityComplaint": "exclamation-circle",
    "WaterQualityComplaintCategory": "tags",
    "SampleCondition": "vial",

    "ComplaintPost": "comments",
    "ComplaintResolution": "check-double",
    "ComplaintAttachment": "paperclip",
    "ComplaintStatusLog": "history",

    "WaterSample": "flask",
    "WaterSampleParameterResult": "chart-line",

    "ComplaintMicrobialAnalysis": "microscope",
    "ComplaintMicrobialParameterResult": "bacteria",

    "ComplaintConfirmationReport": "file-signature",
    "ComplaintAuditTrail": "clipboard-list",
}


# ==========================================================
# GROUP MAP
# ==========================================================
GROUPS = {
    "WaterQualityComplaint": "complaints",
    "WaterQualityComplaintCategory": "complaints",
    "SampleCondition": "complaints",

    "ComplaintPost": "complaints",
    "ComplaintResolution": "complaints",
    "ComplaintAttachment": "complaints",
    "ComplaintStatusLog": "complaints",

    "WaterSample": "laboratory",
    "WaterSampleParameterResult": "laboratory",

    "ComplaintMicrobialAnalysis": "microbial_lab",
    "ComplaintMicrobialParameterResult": "microbial_lab",

    "ComplaintConfirmationReport": "complaints",

    "ComplaintAuditTrail": "audit",
}


# ==========================================================
# DISPLAY HELPERS
# ==========================================================
def humanize_model_name(model) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", model.__name__).strip()


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

def complaint_qs(model) -> QuerySet:
    return model.objects.select_related(
        "user",
        "category",
        "region",
        "zone",
        "sub_zone",
    )


def complaint_post_qs(model) -> QuerySet:
    return model.objects.select_related(
        "complaint",
        "posted_by",
    )


def complaint_resolution_qs(model) -> QuerySet:
    return model.objects.select_related(
        "complaint",
        "resolved_by",
    )


def complaint_attachment_qs(model) -> QuerySet:
    return model.objects.select_related(
        "complaint",
    )


def status_log_qs(model) -> QuerySet:
    return model.objects.select_related(
        "complaint",
        "changed_by",
    )


def water_sample_qs(model) -> QuerySet:
    return model.objects.select_related(
        "complaint",
    ).prefetch_related(
        "conditions",
        "parameter_results",
    )


def sample_parameter_result_qs(model) -> QuerySet:
    return model.objects.select_related(
        "sample",
        "parameter",
        "analyzed_by",
    )


def microbial_analysis_qs(model) -> QuerySet:
    return model.objects.select_related(
        "sample",
        "created_by",
        "analysed_by",
        "verified_by",
        "confirmed_by",
        "approved_by",
    )


def microbial_param_result_qs(model) -> QuerySet:
    return model.objects.select_related(
        "analysis",
        "parameter",
    )


def confirmation_report_qs(model) -> QuerySet:
    return model.objects.select_related(
        "complaint",
        "confirmation_sample",
        "confirmed_by",
    )


def audit_trail_qs(model) -> QuerySet:
    return model.objects.select_related(
        "complaint",
        "performed_by",
    )


# ==========================================================
# REGISTRY WRAPPER
# ==========================================================
def safe_register(model, **kwargs):
    """
    Registry normalization layer.
    """

    if model is None:
        raise RuntimeError("Model resolution failed.")

    meta = kwargs.get("meta", {})
    meta.update(build_meta(model))
    kwargs["meta"] = meta

    ui = kwargs.get("ui", {})
    ui.setdefault("icon", ICONS.get(model.__name__, "shield"))
    ui.setdefault("group", GROUPS.get(model.__name__, "general"))

    kwargs["ui"] = ui

    kwargs.pop("templates", None)

    try:
        return register_model(**kwargs)(model)
    except Exception:
        logger.exception(
            "[wc.registry] Failed registering %s",
            model,
        )
        raise


# ==========================================================
# CORE REGISTRATIONS
# ==========================================================

safe_register(
    WaterQualityComplaint,
    search_fields=[
        "reference_id",
        "title",
        "description",
        "user__username",
    ],
    filter_fields=[
        "status",
        "category",
        "region",
        "zone",
        "sub_zone",
    ],
    ordering=["-created_at"],
    select_related=[
        "user",
        "category",
        "region",
        "zone",
        "sub_zone",
    ],
    queryset_factory=complaint_qs,
    inline_edit_fields=[
        "status",
        "escalation_level",
        "contact_number",
    ],
    bulk_actions={
        "escalate": True,
        "soft_delete": True,
    },
)

safe_register(
    WaterQualityComplaintCategory,
    search_fields=["name"],
    ordering=["name"],
    inline_edit_fields=["name", "description"],
)

safe_register(
    SampleCondition,
    search_fields=["code", "name"],
    ordering=["name"],
    inline_edit_fields=["code", "name"],
)

safe_register(
    ComplaintPost,
    search_fields=["content", "complaint__title"],
    filter_fields=["complaint"],
    ordering=["-posted_at"],
    select_related=["complaint", "posted_by"],
    queryset_factory=complaint_post_qs,
)

safe_register(
    ComplaintResolution,
    search_fields=["resolution_details", "complaint__title"],
    filter_fields=["complaint"],
    ordering=["-resolved_at"],
    select_related=["complaint", "resolved_by"],
    queryset_factory=complaint_resolution_qs,
)

safe_register(
    ComplaintAttachment,
    search_fields=["complaint__title"],
    filter_fields=["complaint"],
    select_related=["complaint"],
    queryset_factory=complaint_attachment_qs,
)

safe_register(
    ComplaintStatusLog,
    search_fields=["previous_status", "new_status"],
    filter_fields=["complaint"],
    ordering=["-changed_at"],
    select_related=["complaint", "changed_by"],
    queryset_factory=status_log_qs,
)

safe_register(
    WaterSample,
    search_fields=["sample_id", "complaint__title"],
    filter_fields=["complaint"],
    select_related=["complaint"],
    queryset_factory=water_sample_qs,
)

safe_register(
    WaterSampleParameterResult,
    search_fields=["parameter__name"],
    filter_fields=["sample", "parameter"],
    select_related=["sample", "parameter", "analyzed_by"],
    queryset_factory=sample_parameter_result_qs,
)

safe_register(
    ComplaintMicrobialAnalysis,
    search_fields=["uuid", "sample__sample_id"],
    filter_fields=["sample", "state"],
    select_related=[
        "sample",
        "created_by",
        "analysed_by",
        "verified_by",
        "confirmed_by",
        "approved_by",
    ],
    queryset_factory=microbial_analysis_qs,
    bulk_actions={
        "transition_state": True,
    },
)

safe_register(
    ComplaintMicrobialParameterResult,
    search_fields=["parameter__parameter__name"],
    filter_fields=["analysis", "parameter"],
    select_related=["analysis", "parameter"],
    queryset_factory=microbial_param_result_qs,
)

safe_register(
    ComplaintConfirmationReport,
    search_fields=["complaint__reference_id"],
    filter_fields=["complaint", "is_confirmed"],
    select_related=["complaint", "confirmation_sample", "confirmed_by"],
    queryset_factory=confirmation_report_qs,
)

safe_register(
    ComplaintAuditTrail,
    search_fields=["action", "complaint__title"],
    filter_fields=["complaint", "performed_by"],
    ordering=["-timestamp"],
    select_related=["complaint", "performed_by"],
    queryset_factory=audit_trail_qs,
)


# ==========================================================
# DEBUG
# ==========================================================
try:
    from core.registry import registry

    logger.info(
        "[wc.registry] loaded app=%s models=%s",
        APP_LABEL,
        len(registry._registry),
    )

except Exception:
    logger.exception(
        "[wc.registry] registry unavailable during import"
    )