from django.contrib import admin
from django.utils.html import format_html
from django.utils.timezone import localtime

from .models import (
    RawWater,
    RawWaterAnalysis,
    JarTest,
    JarResult,
    JarMeasurement,
    CoagulatedWaterLimit
)

# ============================
# Inline Admins
# ============================

class RawWaterAnalysisInline(admin.TabularInline):
    model = RawWaterAnalysis
    extra = 0
    min_num = 1
    show_change_link = True
    autocomplete_fields = ['parameter']


class JarMeasurementInline(admin.TabularInline):
    model = JarMeasurement
    extra = 0
    min_num = 1
    show_change_link = True
    autocomplete_fields = ['parameter']


class JarResultInline(admin.StackedInline):
    model = JarResult
    extra = 0
    show_change_link = True
    readonly_fields = ('performance_rank', 'is_optimal', 'floc_observation_time')
    inlines = [JarMeasurementInline]

    fieldsets = (
        (None, {
            'fields': (
                'jar_number', 'dosage_mg_per_l', 'floc_observation_time',
                'performance_rank', 'is_optimal'
            )
        }),
    )


# ============================
# Admins
# ============================

@admin.register(RawWater)
class RawWaterAdmin(admin.ModelAdmin):
    list_display = (
        'treatment_plant', 'sampled_at', 'coagulant', 'coagulant_concentration_ppm',
        'parameter_count', 'remarks_summary'
    )
    list_filter = ('treatment_plant', 'sampled_at', 'coagulant')
    search_fields = ('treatment_plant__name', 'coagulant__name')
    ordering = ('-sampled_at',)
    inlines = [RawWaterAnalysisInline]
    date_hierarchy = 'sampled_at'
    autocomplete_fields = ['treatment_plant', 'coagulant']

    def parameter_count(self, obj):
        return obj.analyses.count()
    parameter_count.short_description = "Analyses"

    def remarks_summary(self, obj):
        return (obj.remarks[:50] + '...') if obj.remarks else '-'
    remarks_summary.short_description = "Remarks"


@admin.register(JarTest)
class JarTestAdmin(admin.ModelAdmin):
    list_display = (
        'treatment_plant', 'test_date', 'analyst_name', 'established_dosage_mg_per_l',
        'verified_badge', 'confirmed_badge', 'approved_badge'
    )
    list_filter = ('treatment_plant', 'verified_by', 'confirmed_by', 'approved_by')
    search_fields = ('treatment_plant__name', 'analyst__username')
    ordering = ('-test_date',)
    inlines = [JarResultInline]
    autocomplete_fields = ['treatment_plant', 'analyst', 'coagulant']
    actions = ['bulk_verify', 'bulk_confirm', 'bulk_approve']

    def analyst_name(self, obj):
        return obj.analyst.get_full_name() if obj.analyst else '-'

    def verified_badge(self, obj):
        if obj.verified_at:
            return format_html('<span style="color:green;">✔ {}</span>', localtime(obj.verified_at).strftime('%Y-%m-%d'))
        return format_html('<span style="color:red;">✘</span>')
    verified_badge.short_description = 'Verified'

    def confirmed_badge(self, obj):
        if obj.confirmed_at:
            return format_html('<span style="color:blue;">✔ {}</span>', localtime(obj.confirmed_at).strftime('%Y-%m-%d'))
        return format_html('<span style="color:red;">✘</span>')
    confirmed_badge.short_description = 'Confirmed'

    def approved_badge(self, obj):
        if obj.approved_at:
            return format_html('<span style="color:purple;">✔ {}</span>', localtime(obj.approved_at).strftime('%Y-%m-%d'))
        return format_html('<span style="color:red;">✘</span>')
    approved_badge.short_description = 'Approved'

    def bulk_verify(self, request, queryset):
        for test in queryset:
            test.verify(request.user)
            test.save()
        self.message_user(request, "Selected tests have been verified.")
    bulk_verify.short_description = "✔ Bulk Verify"

    def bulk_confirm(self, request, queryset):
        for test in queryset:
            if test.verified_at:
                test.confirm(request.user)
                test.save()
        self.message_user(request, "Verified tests have been confirmed.")
    bulk_confirm.short_description = "✔ Bulk Confirm"

    def bulk_approve(self, request, queryset):
        for test in queryset:
            if test.confirmed_at:
                test.approve(request.user)
                test.save()
        self.message_user(request, "Confirmed tests have been approved.")
    bulk_approve.short_description = "✔ Bulk Approve"


@admin.register(JarResult)
class JarResultAdmin(admin.ModelAdmin):
    list_display = (
        'jar_test', 'jar_number', 'dosage_mg_per_l',
        'performance_rank', 'is_optimal_display', 'floc_observation_time'
    )
    list_filter = ('is_optimal',)
    search_fields = ('jar_test__treatment_plant__name',)
    ordering = ('jar_test__test_date', 'jar_number')
    inlines = [JarMeasurementInline]
    autocomplete_fields = ['jar_test']

    def is_optimal_display(self, obj):
        return format_html('<b style="color:{};">{}</b>',
                           'green' if obj.is_optimal else 'gray',
                           'Yes' if obj.is_optimal else 'No')
    is_optimal_display.short_description = "Optimal?"


@admin.register(JarMeasurement)
class JarMeasurementAdmin(admin.ModelAdmin):
    list_display = ('jar_result', 'parameter', 'value')
    list_filter = ('parameter',)
    search_fields = ('jar_result__jar_test__treatment_plant__name', 'parameter__parameter__name')
    ordering = ('jar_result__jar_test__test_date',)
    autocomplete_fields = ['jar_result', 'parameter']


@admin.register(RawWaterAnalysis)
class RawWaterAnalysisAdmin(admin.ModelAdmin):
    list_display = ('raw_water', 'parameter', 'value')
    search_fields = ('raw_water__treatment_plant__name', 'parameter__parameter__name')
    ordering = ('-raw_water__sampled_at',)
    autocomplete_fields = ['raw_water', 'parameter']



