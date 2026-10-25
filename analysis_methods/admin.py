from django.contrib import admin
from django.utils.html import format_html
import json

from .models import (
    ChemicalAnalysisMethod,
    MicrobialMethod,
    WWAnalysisMethod,
    CWAnalysisMethod,
)


@admin.register(ChemicalAnalysisMethod)
class ChemicalAnalysisMethodAdmin(admin.ModelAdmin):
    list_display = (
        "method",
        "version",
        "kebs_reference",
        "unit",
        "rounding_precision",
        "rounding_mode",
        "category",
        "is_active",
        "created_by",
        "updated_at",
    )
    list_filter = ("is_active", "category", "unit", "rounding_mode", "version", "created_by")
    search_fields = ("method", "kebs_reference", "formula", "description", "category", "tags")
    readonly_fields = (
        "version",
        "formula_hash",
        "created_at",
        "updated_at",
        "example_inputs_pretty",
        "inputs_structure_pretty",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "method",
                    "version",
                    "kebs_reference",
                    "category",
                    "tags",
                    "unit",
                    "rounding_precision",
                    "rounding_mode",
                    "is_active",
                )
            },
        ),
        (
            "Formula & Inputs",
            {
                "description": (
                    "Formula-backed results are calculated automatically from measured fields. "
                    "Define inputs as a JSON list of objects with name, label, unit, help_text, min_value, max_value. "
                    "Example: [{\"name\": \"V\", \"label\": \"Zinc Chloride Titre Volume\", \"unit\": \"mL\", \"min_value\": 0.0, \"max_value\": 20.0}]. "
                    "Saving changes automatically creates a new immutable version and points active chemical specifications to it."
                ),
                "fields": (
                    "formula",
                    "inputs_structure",
                    "inputs_structure_pretty",
                    "example_inputs_pretty",
                    "formula_hash",
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("description", "created_by", "created_at", "updated_at")
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        return False

    def example_inputs_pretty(self, obj):
        payload = obj.example_input_payload() if obj else {}
        return format_html("<pre>{}</pre>", json.dumps(payload, indent=2))

    example_inputs_pretty.short_description = "Example Input Payload"

    def inputs_structure_pretty(self, obj):
        structure = obj.inputs_structure if obj else []
        return format_html("<pre>{}</pre>", json.dumps(structure, indent=2))

    inputs_structure_pretty.short_description = "Inputs Structure (JSON)"

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


# -------------------------
# MicrobialMethod Admin
# -------------------------
@admin.register(MicrobialMethod)
class MicrobialMethodAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "kebs_reference",
        "status",
        "version",
        "is_active",
        "incubation_time",
        "created_by",
        "updated_at",
    )
    list_filter = ("is_active", "status", "version", "created_by")
    search_fields = ("name", "kebs_reference", "description", "confirmatory_tests")
    readonly_fields = (
        "created_at",
        "updated_at",
        "confirmatory_tests_pretty",
        "change_log_pretty",
        "is_deprecated",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "version",
                    "kebs_reference",
                    "status",
                    "is_active",
                    "is_deprecated",
                )
            },
        ),
        (
            "Details",
            {
                "fields": (
                    "description",
                    "incubation_time",
                    "confirmatory_tests_pretty",
                    "change_log_pretty",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_by", "updated_by", "created_at", "updated_at")
            },
        ),
    )
    actions = ["bump_version"]

    def confirmatory_tests_pretty(self, obj):
        return format_html("<pre>{}</pre>", obj.confirmatory_tests)

    confirmatory_tests_pretty.short_description = "Confirmatory Tests"

    def change_log_pretty(self, obj):
        return format_html("<pre>{}</pre>", json.dumps(obj.change_log, indent=2))

    change_log_pretty.short_description = "Change Log (History)"

    def bump_version(self, request, queryset):
        for obj in queryset:
            obj.increment_version(user=request.user, changelog="Version bumped via Admin action.")
        self.message_user(request, f"{queryset.count()} method(s) version bumped successfully.", level="SUCCESS")

    bump_version.short_description = "Increment version for selected methods"

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(WWAnalysisMethod)
class WWAnalysisMethodAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "reference",
        "version",
        "is_active",
        "created_by",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_active", "version", "created_by")
    search_fields = ("name", "reference")
    readonly_fields = ("version", "created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "version",
                    "reference",
                    "is_active",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_by", "updated_by", "created_at", "updated_at")
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CWAnalysisMethod)
class CWAnalysisMethodAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "reference",
        "version",
        "is_active",
        "created_by",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_active", "version", "created_by")
    search_fields = ("name", "reference")
    readonly_fields = ("version", "created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "version",
                    "reference",
                    "is_active",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_by", "updated_by", "created_at", "updated_at")
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
