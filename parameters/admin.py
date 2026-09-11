from django.contrib import admin
from .models import (
    PhysicochemicalParameter, MicrobialParameter, HeavyMetalParameter,
    WWQParameter_qad, CWQParameter_qad, DistributionParameter_qad,
    GigiriParameter_qad, KabeteParameter_qad, CatchmentParameter_qad
)

# --- Base Admin ---
class BaseParameterAdmin(admin.ModelAdmin):
    list_display = ('name', 'unit', 'is_active', 'created_at', 'updated_at')
    list_filter = ('unit', 'is_active', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('uuid', 'created_at', 'updated_at')
    ordering = ('name',)
    actions = ['activate_selected', 'deactivate_selected']

    fieldsets = (
        ('Identification', {
            'fields': ('uuid', 'name', 'unit')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    @admin.action(description='Activate selected parameters')
    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} parameters activated.")

    @admin.action(description='Deactivate (soft-delete) selected parameters')
    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} parameters deactivated.")

# --- Standardized Parameters Admin Mixin ---
class StandardizedParameterAdminMixin(admin.ModelAdmin):
    def get_list_display(self, request):
        return super().get_list_display(request) + ('min_standard', 'max_standard')

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        return fieldsets + (
            ('Standards', {
                'fields': ('min_standard', 'max_standard')
            }),
        )

# --- Non-Standardized Parameter Admins ---
@admin.register(PhysicochemicalParameter)
class PhysicochemicalParameterAdmin(BaseParameterAdmin):
    pass

@admin.register(MicrobialParameter)
class MicrobialParameterAdmin(BaseParameterAdmin):
    pass

@admin.register(HeavyMetalParameter)
class HeavyMetalParameterAdmin(BaseParameterAdmin):
    pass

@admin.register(CatchmentParameter_qad)
class CatchmentParameterAdmin(BaseParameterAdmin):
    pass

# --- Standardized Parameter Admins ---
@admin.register(WWQParameter_qad)
class WWQParameterAdmin(StandardizedParameterAdminMixin, BaseParameterAdmin):
    pass

@admin.register(CWQParameter_qad)
class CWQParameterAdmin(StandardizedParameterAdminMixin, BaseParameterAdmin):
    pass

@admin.register(DistributionParameter_qad)
class DistributionParameterAdmin(StandardizedParameterAdminMixin, BaseParameterAdmin):
    pass

@admin.register(GigiriParameter_qad)
class GigiriParameterAdmin(StandardizedParameterAdminMixin, BaseParameterAdmin):
    pass

@admin.register(KabeteParameter_qad)
class KabeteParameterAdmin(StandardizedParameterAdminMixin, BaseParameterAdmin):
    pass
