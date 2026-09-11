from django.contrib import admin
from django.utils.html import format_html
from django.http import HttpResponse
import csv

from .models import ChlorineDemandTest, ChlorineJarResult


class ChlorineJarResultInline(admin.TabularInline):
    model = ChlorineJarResult
    extra = 0
    readonly_fields = ('performance_rank', 'is_optimal_badge', 'created_at')
    fields = ('jar_number', 'dosage_mg_per_l', 'residual_chlorine', 'performance_rank', 'is_optimal_badge', 'created_at')

    def is_optimal_badge(self, obj):
        if obj.is_optimal:
            return format_html('<span style="color: green; font-weight: bold;">✔ Optimal</span>')
        return format_html('<span style="color: gray;">—</span>')
    is_optimal_badge.short_description = "Optimal"


@admin.register(ChlorineDemandTest)
class ChlorineDemandTestAdmin(admin.ModelAdmin):
    list_display = (
        'treatment_plant',
        'test_date',
        'analyst',
        'established_dosage_mg_per_l',
        'verified_at',
        'confirmed_at',
        'approved_at',
    )
    list_filter = ('treatment_plant', 'verified_at', 'confirmed_at', 'approved_at')
    search_fields = ('treatment_plant__name', 'analyst__username')
    date_hierarchy = 'test_date'
    readonly_fields = (
        'created_at',
        'verified_by', 'verified_at',
        'confirmed_by', 'confirmed_at',
        'approved_by', 'approved_at',
    )
    inlines = [ChlorineJarResultInline]
    actions = ['export_as_csv']

    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=chlorine_tests.csv'
        writer = csv.writer(response)
        writer.writerow([
            'Plant', 'Date', 'Analyst',
            'Dosage (mg/L)', 'Verified', 'Confirmed', 'Approved'
        ])
        for obj in queryset:
            writer.writerow([
                obj.treatment_plant.name,
                obj.test_date,
                obj.analyst.get_full_name() if obj.analyst else '',
                obj.established_dosage_mg_per_l,
                bool(obj.verified_at),
                bool(obj.confirmed_at),
                bool(obj.approved_at)
            ])
        return response
    export_as_csv.short_description = "Export Selected as CSV"


@admin.register(ChlorineJarResult)
class ChlorineJarResultAdmin(admin.ModelAdmin):
    list_display = ('test', 'jar_number', 'dosage_mg_per_l', 'residual_chlorine', 'performance_rank', 'is_optimal', 'created_at')
    list_filter = ('is_optimal', 'test__treatment_plant')
    search_fields = ('test__treatment_plant__name',)
