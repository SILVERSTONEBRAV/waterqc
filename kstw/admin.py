from django.contrib import admin, messages
from django.urls import path
from django.utils.html import format_html
from django.shortcuts import redirect
from django.db import transaction
from .models import (
    WasteWaterSamplingSite, WasteWaterSample, WasteWaterAnalysis, WasteWaterParameterResult,
    IndustrialSample, IndustrialSampleAnalysis, IndustrialSampleParameterResult,
    TreatmentPlantSample, TreatmentPlantSampleAnalysis, TreatmentPlantSampleParameterResult,
    ExhausterSample, ExhausterSampleAnalysis, ExhausterSampleParameterResult,
    WaterAnalysisState, STATE_TRANSITIONS, STATE_PERMISSIONS, STATE_USER_FIELD
)


class ParameterResultInline(admin.TabularInline):
    extra = 1
    autocomplete_fields = ['parameter', 'analysis_method']
    fields = ('parameter', 'result', 'effluent_standard', 'kebs_reference', 'quality_compliance')
    readonly_fields = ('effluent_standard', 'kebs_reference', 'quality_compliance')


class WasteWaterParameterResultInline(ParameterResultInline):
    model = WasteWaterParameterResult


class IndustrialSampleParameterResultInline(ParameterResultInline):
    model = IndustrialSampleParameterResult


class TreatmentPlantSampleParameterResultInline(ParameterResultInline):
    model = TreatmentPlantSampleParameterResult


class ExhausterSampleParameterResultInline(ParameterResultInline):
    model = ExhausterSampleParameterResult


class TransitionActionsMixin:
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:pk>/verify/', self.admin_site.admin_view(self.process_verify), name=f'{self.model._meta.model_name}-verify'),
            path('<int:pk>/confirm/', self.admin_site.admin_view(self.process_confirm), name=f'{self.model._meta.model_name}-confirm'),
        ]
        return custom_urls + urls

    def process_verify(self, request, pk):
        return self._process_transition(request, pk, WaterAnalysisState.VERIFIED)

    def process_confirm(self, request, pk):
        return self._process_transition(request, pk, WaterAnalysisState.CONFIRMED)

    def _process_transition(self, request, pk, target_state):
        obj = self.model.objects.get(pk=pk)
        try:
            with transaction.atomic():
                obj.change_status(target_state, request.user, user_has_permission=True)
            self.message_user(request, f"{self.model.__name__} {obj} transitioned to {target_state}.", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error: {e}", level=messages.ERROR)
        return redirect(request.META.get('HTTP_REFERER'))

    def colored_status(self, obj):
        color = {
            WaterAnalysisState.NEW: 'gray',
            WaterAnalysisState.ANALYSED: 'orange',
            WaterAnalysisState.VERIFIED: 'blue',
            WaterAnalysisState.CONFIRMED: 'green',
            WaterAnalysisState.APPROVED: 'darkgreen',
        }.get(obj.status, 'black')
        return format_html('<b style="color:{}">{}</b>', color, obj.get_status_display())
    colored_status.short_description = 'Status'

    def action_buttons(self, obj):
        buttons = ''
        if obj.status != WaterAnalysisState.VERIFIED:
            buttons += f'<a class="button" style="margin-right:5px;" href="{obj.pk}/verify/">Verify</a>'
        if obj.status != WaterAnalysisState.CONFIRMED:
            buttons += f'<a class="button" href="{obj.pk}/confirm/">Confirm</a>'
        return format_html(buttons)
    action_buttons.short_description = 'Actions'

@admin.register(WasteWaterSamplingSite)
class WasteWaterSamplingSiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'treatment_plant', 'location_description')


@admin.register(WasteWaterSample)
class WasteWaterSampleAdmin(admin.ModelAdmin):
    list_display = ('reference_id', 'sampling_site', 'treatment_plant', 'sampling_date', 'sampling_time')
    search_fields = ('reference_id',)
    list_filter = ('treatment_plant', 'sampling_site')


@admin.register(WasteWaterAnalysis)
class WasteWaterAnalysisAdmin(TransitionActionsMixin, admin.ModelAdmin):
    list_display = ('sample', 'colored_status', 'analysis_datetime', 'action_buttons')
    inlines = [WasteWaterParameterResultInline]


@admin.register(IndustrialSample)
class IndustrialSampleAdmin(admin.ModelAdmin):
    list_display = ('reference_id', 'client_name', 'location', 'sampling_date')


@admin.register(IndustrialSampleAnalysis)
class IndustrialSampleAnalysisAdmin(TransitionActionsMixin, admin.ModelAdmin):
    list_display = ('sample', 'colored_status', 'analysis_datetime', 'action_buttons')
    inlines = [IndustrialSampleParameterResultInline]


@admin.register(TreatmentPlantSample)
class TreatmentPlantSampleAdmin(admin.ModelAdmin):
    list_display = ('reference_id', 'treatment_plant', 'sampling_point_description', 'sampling_date')


@admin.register(TreatmentPlantSampleAnalysis)
class TreatmentPlantSampleAnalysisAdmin(TransitionActionsMixin, admin.ModelAdmin):
    list_display = ('sample', 'colored_status', 'analysis_datetime', 'action_buttons')
    inlines = [TreatmentPlantSampleParameterResultInline]


@admin.register(ExhausterSample)
class ExhausterSampleAdmin(admin.ModelAdmin):
    list_display = ('reference_id', 'exhauster_reg_number', 'driver_name', 'sampling_date')


@admin.register(ExhausterSampleAnalysis)
class ExhausterSampleAnalysisAdmin(TransitionActionsMixin, admin.ModelAdmin):
    list_display = ('sample', 'colored_status', 'analysis_datetime', 'action_buttons')
    inlines = [ExhausterSampleParameterResultInline]
