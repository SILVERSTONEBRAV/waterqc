from django.contrib import admin
from .models import AuditLogEntry, UserActivity
from django.http import HttpResponse
import csv

class UserActivityInline(admin.TabularInline):
    model = UserActivity
    extra = 0
    readonly_fields = ['user', 'ip_address', 'timestamp', 'successful_attempt', 'user_agent', 'activity_type', 'duration', 'location']
    can_delete = False

def export_as_csv(modeladmin, request, queryset):
    meta = modeladmin.model._meta
    field_names = [field.name for field in meta.fields]

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={meta}.csv'
    writer = csv.writer(response)

    writer.writerow(field_names)
    for obj in queryset:
        row = writer.writerow([getattr(obj, field) for field in field_names])

    return response

export_as_csv.short_description = "Export Selected as CSV"

class AuditLogEntryAdmin(admin.ModelAdmin):
    inlines = [UserActivityInline]
    list_display = ['user', 'result_status', 'timestamp', 'priority', 'ip_address', 'user_agent', 'location', 'additional_data', 'description']
    search_fields = ['user__username', 'result_status', 'ip_address', 'user_agent', 'location', 'description']
    readonly_fields = ['user', 'result_status', 'timestamp', 'ip_address', 'user_agent', 'location', 'additional_data', 'description', 'priority']
    fieldsets = (
        (None, {
            'fields': ('user', 'result_status', 'timestamp', 'priority')
        }),
        ('Details', {
            'fields': ('ip_address', 'user_agent', 'location', 'additional_data', 'description')
        }),
    )
    actions = [export_as_csv]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'audit_entry', 'ip_address', 'timestamp', 'successful_attempt', 'user_agent', 'activity_type', 'duration', 'location']
    search_fields = ['user__username', 'audit_entry__action', 'activity_type', 'ip_address', 'user_agent', 'location']
    readonly_fields = ['user', 'audit_entry', 'ip_address', 'timestamp', 'successful_attempt', 'user_agent', 'activity_type', 'duration', 'location']
    actions = [export_as_csv]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(AuditLogEntry, AuditLogEntryAdmin)
admin.site.register(UserActivity, UserActivityAdmin)
