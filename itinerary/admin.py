from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from .models import (
    SamplingPlan, DynamicSamplingPoint, Itinerary, SampleCategory,
    RegionSamplingPoint, FCARegionSamplingPoint, CatchmentSamplingPoint
)

# --- Inline Sampling Points in Itinerary ---
class DynamicSamplingPointInline(admin.TabularInline):
    model = Itinerary.sampling_points.through
    extra = 1
    verbose_name = "Assigned Sampling Point"
    verbose_name_plural = "Assigned Sampling Points"

# --- Itinerary Admin ---
@admin.register(Itinerary)
class ItineraryAdmin(admin.ModelAdmin):
    list_display = ('name', 'sampling_date', 'status', 'is_locked', 'max_sampling_points', 'remaining_slots', 'lock_action', 'complete_action')
    list_filter = ('status', 'sampling_date', 'is_locked')
    search_fields = ('name',)
    ordering = ('-sampling_date',)
    inlines = [DynamicSamplingPointInline]
    readonly_fields = ('remaining_slots', 'is_full', 'status', 'content_type', 'object_id')

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_locked:
            # Lock all fields when Itinerary is locked except admin actions
            return self.readonly_fields + tuple([f.name for f in obj._meta.fields if f.name not in ['id']])
        return self.readonly_fields

    # Custom Admin Action Buttons
    def lock_action(self, obj):
        if not obj.is_locked:
            return format_html('<a class="button" href="{}">Lock</a>', f'lock/{obj.pk}/')
        return "Locked"
    lock_action.short_description = 'Lock Itinerary'

    def complete_action(self, obj):
        if obj.status != 'Completed':
            return format_html('<a class="button" href="{}">Complete</a>', f'complete/{obj.pk}/')
        return "Completed"
    complete_action.short_description = 'Complete Itinerary'

    # Custom Admin URLs for Actions
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('lock/<uuid:pk>/', self.admin_site.admin_view(self.process_lock), name='itinerary-lock'),
            path('complete/<uuid:pk>/', self.admin_site.admin_view(self.process_complete), name='itinerary-complete'),
        ]
        return custom_urls + urls

    def process_lock(self, request, pk):
        itinerary = self.get_object(request, pk)
        if itinerary.is_locked:
            self.message_user(request, "Itinerary is already locked.", messages.WARNING)
        else:
            itinerary.lock()
            self.message_user(request, "Itinerary locked successfully.", messages.SUCCESS)
        return redirect(request.META.get('HTTP_REFERER', 'admin:index'))

    def process_complete(self, request, pk):
        itinerary = self.get_object(request, pk)
        if itinerary.status == 'Completed':
            self.message_user(request, "Itinerary is already completed.", messages.WARNING)
        else:
            itinerary.mark_completed()
            self.message_user(request, "Itinerary marked as completed.", messages.SUCCESS)
        return redirect(request.META.get('HTTP_REFERER', 'admin:index'))

# --- Sampling Plan Admin ---
@admin.register(SamplingPlan)
class SamplingPlanAdmin(admin.ModelAdmin):
    list_display = ('month', 'target_sampling_points', 'actual_sampled_points', 'coverage_percentage', 'refresh_actuals_action')
    ordering = ('-month',)
    readonly_fields = ('actual_sampled_points', 'coverage_percentage')

    def refresh_actuals_action(self, obj):
        return format_html('<a class="button" href="{}">Refresh</a>', f'refresh/{obj.pk}/')
    refresh_actuals_action.short_description = 'Refresh Actuals'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('refresh/<uuid:pk>/', self.admin_site.admin_view(self.process_refresh), name='samplingplan-refresh'),
        ]
        return custom_urls + urls

    def process_refresh(self, request, pk):
        plan = self.get_object(request, pk)
        plan.refresh_actual_sampled_points()
        self.message_user(request, "Actual sampled points refreshed.", messages.SUCCESS)
        return redirect(request.META.get('HTTP_REFERER', 'admin:index'))

# --- DynamicSamplingPoint Admin (ReadOnly) ---
@admin.register(DynamicSamplingPoint)
class DynamicSamplingPointAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'content_type', 'object_id', 'is_sampled_this_month', 'last_sampled_date', 'is_active')
    readonly_fields = ('content_type', 'object_id', 'last_sampled_date', 'is_sampled_this_month', 'is_active')
    search_fields = ('object_id',)

# --- SampleCategory Admin ---
@admin.register(SampleCategory)
class SampleCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    search_fields = ('name',)

# --- Register Sampling Point Types ---
@admin.register(RegionSamplingPoint)
class RegionSamplingPointAdmin(admin.ModelAdmin):
    list_display = ('name', 'region', 'last_sampled_date', 'total_times_sampled', 'is_sampled_this_month')
    search_fields = ('name', 'region__name')

@admin.register(FCARegionSamplingPoint)
class FCARegionSamplingPointAdmin(admin.ModelAdmin):
    list_display = ('name', 'fca_region_name', 'last_sampled_date', 'total_times_sampled', 'is_sampled_this_month')
    search_fields = ('name', 'fca_region_name')

@admin.register(CatchmentSamplingPoint)
class CatchmentSamplingPointAdmin(admin.ModelAdmin):
    list_display = ('name', 'catchment', 'last_sampled_date', 'total_times_sampled', 'is_sampled_this_month')
    search_fields = ('name', 'catchment__name')
