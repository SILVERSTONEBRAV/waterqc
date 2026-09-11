from django.contrib import admin
from django.utils.html import format_html

from .models import (
    SamplingSchedule,
    SamplingTime,
    WaterAnalysis,

    RawWaterResult,
    TreatedWaterResult,
    CoagulatedWaterResult,
    ClarifiedWaterResult,

    Cause,
    NonConformity,
    NonConformityLog,
    WaterAnalysisLog,
)


# ======================================================
# SAMPLING
# ======================================================

class SamplingTimeInline(admin.TabularInline):

    model = SamplingTime

    extra = 0

    readonly_fields = (
        "time",
        "sequence_display",
    )

    ordering = (
        "time",
    )


    def sequence_display(self, obj):

        return (
            f"{obj.sequence}/"
            f"{obj.total_samples}"
        )

    sequence_display.short_description = "Sequence"



@admin.register(SamplingSchedule)
class SamplingScheduleAdmin(admin.ModelAdmin):

    list_display = (
        "treatment_plant",
        "water_type",
        "start_time",
        "interval_minutes",
        "generated_count_display",
        "health_display",
        "enabled",
        "last_generated_at",
    )


    list_filter = (
        "water_type",
        "enabled",
        "treatment_plant",
    )


    search_fields = (
        "treatment_plant__name",
    )


    readonly_fields = (
        "last_generated_at",
        "generated_count_display",
        "samples_per_day",
        "is_healthy",
    )


    inlines = [
        SamplingTimeInline,
    ]


    def generated_count_display(self,obj):

        return obj.generated_count

    generated_count_display.short_description = (
        "Generated Times"
    )


    def health_display(self,obj):

        if obj.is_healthy:
            return format_html(
                '<span style="color:green;">HEALTHY</span>'
            )

        return format_html(
            '<span style="color:red;">INCOMPLETE</span>'
        )


    health_display.short_description = "Status"



@admin.register(SamplingTime)
class SamplingTimeAdmin(admin.ModelAdmin):

    list_display = (
        "schedule",
        "water_type_display",
        "time",
        "sequence",
        "minutes_until",
    )


    list_filter = (
        "schedule__water_type",
        "schedule__treatment_plant",
    )


    search_fields = (
        "schedule__treatment_plant__name",
    )


    readonly_fields = (
        "sequence",
        "total_samples",
        "next_datetime",
        "previous_datetime",
    )


    def water_type_display(self,obj):

        return obj.schedule.get_water_type_display()

    water_type_display.short_description = "Water Type"



# ======================================================
# RESULT INLINES
# ======================================================

class ResultBaseInline(admin.TabularInline):

    extra = 0

    fields = (
        "parameter",
        "phase",
        "value",
    )

    readonly_fields = (
        "parameter",
        "phase",
    )



class RawWaterResultInline(ResultBaseInline):

    model = RawWaterResult



class TreatedWaterResultInline(ResultBaseInline):

    model = TreatedWaterResult



class CoagulatedWaterResultInline(ResultBaseInline):

    model = CoagulatedWaterResult



class ClarifiedWaterResultInline(ResultBaseInline):

    model = ClarifiedWaterResult



# ======================================================
# WATER ANALYSIS
# ======================================================


class WaterAnalysisLogInline(admin.TabularInline):

    model = WaterAnalysisLog

    extra = 0

    readonly_fields = (
        "actor",
        "action",
        "remarks",
        "auto_generated",
        "created_at",
    )

    can_delete = False



@admin.register(WaterAnalysis)
class WaterAnalysisAdmin(admin.ModelAdmin):

    list_display = (
        "reference_id",
        "treatment_plant",
        "water_type_display",
        "analysis_date",
        "analysis_time_display",
        "shift",
        "result_status",
    )


    list_filter = (
        "analysis_date",
        "shift",
        "analysis_time__schedule__water_type",
        "treatment_plant",
    )


    search_fields = (
        "reference_id",
        "treatment_plant__name",
    )


    readonly_fields = (
        "reference_id",
        "water_type_display",
        "created_at",
        "updated_at",
    )


    date_hierarchy = (
        "analysis_date"
    )


    inlines = [
        RawWaterResultInline,
        TreatedWaterResultInline,
        CoagulatedWaterResultInline,
        ClarifiedWaterResultInline,
        WaterAnalysisLogInline,
    ]


    def water_type_display(self,obj):

        return obj.analysis_time.schedule.get_water_type_display()


    water_type_display.short_description = (
        "Water Type"
    )


    def analysis_time_display(self,obj):

        return obj.analysis_time.time.strftime(
            "%H:%M"
        )


    analysis_time_display.short_description = (
        "Time"
    )


    def result_status(self,obj):

        total = 0

        entered = 0


        for rel in (
            "rawwaterresults",
            "treatedwaterresults",
            "coagulatedwaterresults",
            "clarifiedwaterresults",
        ):

            qs = getattr(
                obj,
                rel,
                None
            )

            if qs:

                count = qs.count()

                total += count

                entered += qs.filter(
                    value__isnull=False
                ).count()


        if total == 0:
            return "NO RESULTS"


        return (
            f"{entered}/{total}"
        )


    result_status.short_description = (
        "Results"
    )



# ======================================================
# RESULT ADMIN
# ======================================================


@admin.register(RawWaterResult)
class RawWaterResultAdmin(admin.ModelAdmin):

    list_display = (
        "analysis",
        "parameter",
        "value",
    )

    list_filter = (
        "analysis__treatment_plant",
    )



@admin.register(TreatedWaterResult)
class TreatedWaterResultAdmin(admin.ModelAdmin):

    list_display = (
        "analysis",
        "phase",
        "parameter",
        "value",
    )


    list_filter = (
        "phase",
        "analysis__treatment_plant",
    )



@admin.register(CoagulatedWaterResult)
class CoagulatedWaterResultAdmin(admin.ModelAdmin):

    list_display = (
        "analysis",
        "phase",
        "parameter",
        "value",
    )


    list_filter = (
        "phase",
        "analysis__treatment_plant",
    )



@admin.register(ClarifiedWaterResult)
class ClarifiedWaterResultAdmin(admin.ModelAdmin):

    list_display = (
        "analysis",
        "phase",
        "parameter",
        "value",
    )


    list_filter = (
        "phase",
        "analysis__treatment_plant",
    )



# ======================================================
# NON CONFORMITY
# ======================================================


@admin.register(Cause)
class CauseAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "created_by",
        "created_at",
    )

    search_fields = (
        "name",
    )



class NonConformityLogInline(admin.TabularInline):

    model = NonConformityLog

    extra = 0

    readonly_fields = (
        "actor",
        "action",
        "remarks",
        "auto_generated",
        "created_at",
    )



@admin.register(NonConformity)
class NonConformityAdmin(admin.ModelAdmin):

    list_display = (
        "parameter_name",
        "analysis",
        "observed_value",
        "status",
        "risk_score",
        "auto_detected",
        "created_at",
    )


    list_filter = (
        "status",
        "auto_detected",
        "analysis__treatment_plant",
    )


    search_fields = (
        "parameter_name",
        "analysis__reference_id",
    )


    readonly_fields = (
        "risk_score",
        "created_at",
        "updated_at",
    )


    inlines = [
        NonConformityLogInline,
    ]



@admin.register(NonConformityLog)
class NonConformityLogAdmin(admin.ModelAdmin):

    list_display = (
        "nonconformity",
        "action",
        "actor",
        "auto_generated",
        "created_at",
    )


    readonly_fields = (
        "nonconformity",
        "actor",
        "action",
        "remarks",
        "auto_generated",
        "created_at",
    )



# ======================================================
# WATER ANALYSIS LOG
# ======================================================


@admin.register(WaterAnalysisLog)
class WaterAnalysisLogAdmin(admin.ModelAdmin):

    list_display = (
        "analysis",
        "action",
        "actor",
        "auto_generated",
        "created_at",
    )


    list_filter = (
        "action",
        "auto_generated",
    )


    readonly_fields = (
        "analysis",
        "actor",
        "action",
        "remarks",
        "auto_generated",
        "created_at",
    )