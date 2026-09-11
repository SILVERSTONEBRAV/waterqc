from django.contrib import admin
from .models import (
    TreatmentPlant, TreatmentPlantPhase, FilterType, WaterFilter,
    Clarifier, DisludgeValve, Status,
    TreatedWaterLimit, MicrobialLimit, HeavyMetalLimit,
    RawWaterLimit, ClarifiedWaterLimit, CoagulatedWaterLimit, FilteredWaterLimit
)


# ========================
# Inline Admins
# ========================

class TreatmentPlantPhaseInline(admin.TabularInline):
    model = TreatmentPlantPhase
    extra = 0


class WaterFilterInline(admin.TabularInline):
    model = WaterFilter
    extra = 0


class ClarifierInline(admin.TabularInline):
    model = Clarifier
    extra = 0


class DisludgeValveInline(admin.TabularInline):
    model = DisludgeValve
    extra = 0


class TreatedWaterLimitInline(admin.TabularInline):
    model = TreatedWaterLimit
    extra = 0


class MicrobialLimitInline(admin.TabularInline):
    model = MicrobialLimit
    extra = 0


class HeavyMetalLimitInline(admin.TabularInline):
    model = HeavyMetalLimit
    extra = 0


class RawWaterLimitInline(admin.TabularInline):
    model = RawWaterLimit
    extra = 0


class ClarifiedWaterLimitInline(admin.TabularInline):
    model = ClarifiedWaterLimit
    extra = 0


class CoagulatedWaterLimitInline(admin.TabularInline):
    model = CoagulatedWaterLimit
    extra = 0


class FilteredWaterLimitInline(admin.TabularInline):
    model = FilteredWaterLimit
    extra = 0


# ========================
# Admin Classes
# ========================

@admin.register(TreatmentPlant)
class TreatmentPlantAdmin(admin.ModelAdmin):
    list_display = ['name', 'location']
    search_fields = ['name', 'location']
    inlines = [
        TreatmentPlantPhaseInline,
        WaterFilterInline,
        ClarifierInline,
        TreatedWaterLimitInline,
        MicrobialLimitInline,
        HeavyMetalLimitInline,
        RawWaterLimitInline,
        ClarifiedWaterLimitInline,
        CoagulatedWaterLimitInline,
        FilteredWaterLimitInline
    ]


@admin.register(TreatmentPlantPhase)
class TreatmentPlantPhaseAdmin(admin.ModelAdmin):
    list_display = ['name', 'treatment_plant', 'design_capacity', 'operational_capacity']
    list_filter = ['treatment_plant']
    search_fields = ['name']



@admin.register(FilterType)
class FilterTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']


@admin.register(WaterFilter)
class WaterFilterAdmin(admin.ModelAdmin):
    list_display = ['name', 'filter_type', 'status', 'flow_rate', 'treatment_plant', 'phase', 'volume']
    readonly_fields = ['volume']
    list_filter = ['filter_type', 'status', 'treatment_plant']
    search_fields = ['name', 'location']
    date_hierarchy = 'installation_date'


@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(Clarifier)
class ClarifierAdmin(admin.ModelAdmin):
    list_display = ['name', 'design', 'flow_type', 'design_capacity', 'treatment_plant']
    list_filter = ['design', 'flow_type', 'treatment_plant']
    search_fields = ['name']
    inlines = [DisludgeValveInline]
    date_hierarchy = 'installation_date'


@admin.register(DisludgeValve)
class DisludgeValveAdmin(admin.ModelAdmin):
    list_display = ['name', 'clarifier', 'status']
    list_filter = ['status']
    search_fields = ['name']


# ========================
# Limit Admins (Generic)
# ========================

class BaseLimitAdmin(admin.ModelAdmin):
    list_display = ['parameter', 'treatment_plant', 'min_value', 'max_value']
    list_filter = ['treatment_plant', 'parameter']
    search_fields = ['parameter__name']


@admin.register(TreatedWaterLimit)
class TreatedWaterLimitAdmin(BaseLimitAdmin): pass

@admin.register(MicrobialLimit)
class MicrobialLimitAdmin(BaseLimitAdmin): pass

@admin.register(HeavyMetalLimit)
class HeavyMetalLimitAdmin(BaseLimitAdmin): pass

@admin.register(RawWaterLimit)
class RawWaterLimitAdmin(BaseLimitAdmin): pass

@admin.register(ClarifiedWaterLimit)
class ClarifiedWaterLimitAdmin(BaseLimitAdmin): pass

@admin.register(CoagulatedWaterLimit)
class CoagulatedWaterLimitAdmin(BaseLimitAdmin): pass

@admin.register(FilteredWaterLimit)
class FilteredWaterLimitAdmin(BaseLimitAdmin): pass
