from django.contrib import admin
from django.utils.html import format_html
import json

from .models import (
    ChemicalAnalysisMethod,
    MicrobialMethod,
    WWAnalysisMethod,
    CWAnalysisMethod
)

@admin.register(ChemicalAnalysisMethod)
class ChemicalAnalysisMethodAdmin(admin.ModelAdmin):
    list_display = ("method", "version", "unit", "category", "is_active", "created_by", "created_at", "updated_at")
    list_filter = ("is_active", "category", "unit", "version", "created_by")
    search_fields = ("method", "description", "category", "tags")
    readonly_fields = ("formula_hash", "created_at", "updated_at", "example_inputs_pretty", "inputs_structure_pretty")
    fieldsets = (
        (None, {
            "fields": ("method", "version", "kebs_reference", "category", "tags", "unit", "rounding_precision", "is_active")
        }),
        ("Formula & Inputs", {
            "fields": ("formula", "inputs_structure_pretty", "example_inputs_pretty", "formula_hash")
        }),
        ("Metadata", {
            "fields": ("description", "created_by", "created_at", "updated_at")
        }),
    )

    def example_inputs_pretty(self, obj):
        return format_html("<pre>{}</pre>", json.dumps(obj.example_input_payload(), indent=2))
    example_inputs_pretty.short_description = "Example Input Payload"

    def inputs_structure_pretty(self, obj):
        return format_html("<pre>{}</pre>", json.dumps(obj.inputs_structure, indent=2))
    inputs_structure_pretty.short_description = "Inputs Structure (JSON)"

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

# -------------------------
# MicrobialMethod Admin
# -------------------------
@admin.register(MicrobialMethod)
class MicrobialMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "kebs_reference", "status", "version", "is_active", "incubation_time", "created_by", "updated_at")
    list_filter = ("is_active", "status", "version", "created_by")
    search_fields = ("name", "kebs_reference", "description", "confirmatory_tests")
    readonly_fields = ("created_at", "updated_at", "confirmatory_tests_pretty", "change_log_pretty", "is_deprecated")
    fieldsets = (
        (None, {
            "fields": ("name", "version", "kebs_reference", "status", "is_active", "is_deprecated")
        }),
        ("Details", {
            "fields": ("description", "incubation_time", "confirmatory_tests_pretty", "change_log_pretty")
        }),
        ("Metadata", {
            "fields": ("created_by", "created_at", "updated_at")
        }),
    )
    actions = ['bump_version']

    def confirmatory_tests_pretty(self, obj):
        return format_html("<pre>{}</pre>", obj.confirmatory_tests)
    confirmatory_tests_pretty.short_description = "Confirmatory Tests"

    def change_log_pretty(self, obj):
        return format_html("<pre>{}</pre>", json.dumps(obj.change_log, indent=2))
    change_log_pretty.short_description = "Change Log (History)"

    def bump_version(self, request, queryset):
        for obj in queryset:
            obj.increment_version(user=request.user, changelog="Version bumped via Admin action.")
        self.message_user(request, f"{queryset.count()} method(s) version bumped successfully.", level='SUCCESS')
    bump_version.short_description = "Increment version for selected methods"

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(WWAnalysisMethod)
class WWAnalysisMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "reference")
    search_fields = ("name", "reference")

@admin.register(CWAnalysisMethod)
class CWAnalysisMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "reference")
    search_fields = ("name", "reference")
