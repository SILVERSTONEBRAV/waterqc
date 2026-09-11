from django.contrib import admin
from .models import (
    OperationStatus,
    PhaseLossRate,
    Backwashing,
    Disludging,
    PumpFlush
)


@admin.register(OperationStatus)
class OperationStatusAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']
    search_fields = ['name']


@admin.register(PhaseLossRate)
class PhaseLossRateAdmin(admin.ModelAdmin):
    list_display = ['id', 'phase', 'operation', 'loss_rate_m3pm', 'effective_date']
    list_filter = ['phase', 'operation', 'effective_date']
    search_fields = ['phase__name']
    ordering = ['-effective_date']


@admin.register(Backwashing)
class BackwashingAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'treatment_plant', 'filter_unit', 'phase', 'performed_by',
        'start_time', 'end_time', 'duration_minutes', 'water_lost_m3', 'status'
    ]
    list_filter = ['treatment_plant', 'phase', 'status', 'start_time']
    search_fields = ['filter_unit__name', 'performed_by__username']
    readonly_fields = ['duration_minutes', 'water_lost_m3']
    date_hierarchy = 'start_time'


@admin.register(Disludging)
class DisludgingAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'treatment_plant', 'clarifier', 'phase', 'performed_by',
        'start_time', 'end_time', 'duration_minutes', 'water_lost_m3', 'status'
    ]
    list_filter = ['treatment_plant', 'phase', 'status', 'start_time']
    search_fields = ['clarifier__name', 'performed_by__username']
    readonly_fields = ['duration_minutes', 'water_lost_m3']
    date_hierarchy = 'start_time'


@admin.register(PumpFlush)
class PumpFlushAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'treatment_plant', 'chemical_pump', 'phase', 'performed_by',
        'start_time', 'end_time', 'duration_minutes', 'water_lost_m3', 'status'
    ]
    list_filter = ['treatment_plant', 'phase', 'status', 'start_time']
    search_fields = ['chemical_pump__name', 'performed_by__username']
    readonly_fields = ['duration_minutes', 'water_lost_m3']
    date_hierarchy = 'start_time'
