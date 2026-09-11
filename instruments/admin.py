# instruments/admin.py
import json
import logging
from django.contrib import admin
from django.utils.html import format_html
from django.utils.timezone import now
from django.urls import path
from django.template.response import TemplateResponse

from .models import (
    Instrument,
    Sensor,
    OnlineMeasurement,
    DerivedMetric,
    InstrumentCalibration,
    SensorHealthSnapshot,
)

logger = logging.getLogger(__name__)

# =====================================================
# Helper: Color-coded status / health
# =====================================================
def colored_status(status):
    colors = {
        'online': 'green',
        'offline': 'red',
        'degraded': 'orange',
        'fault': 'darkred',
        'maintenance': 'blue',
    }
    color = colors.get(status, 'black')
    return format_html('<span style="color: {};"><strong>{}</strong></span>', color, status.capitalize())

def health_badge(score):
    try:
        score = float(score)
    except Exception:
        score = 0
    if score >= 90:
        color = 'green'
    elif score >= 70:
        color = 'orange'
    else:
        color = 'red'
    return format_html('<span style="color:{}; font-weight:bold;">{:.0f}%</span>', color, score)

# =====================================================
# Inline Admins
# =====================================================
class SensorInline(admin.TabularInline):
    model = Sensor
    extra = 0
    readonly_fields = ('treatment_plant', 'phase', 'uuid')
    fields = ('name', 'parameter', 'stage', 'unit', 'is_primary', 'is_active', 'treatment_plant', 'phase')

class CalibrationInline(admin.TabularInline):
    model = InstrumentCalibration
    extra = 0
    readonly_fields = ('performed_at',)
    fields = ('performed_at', 'performed_by', 'method', 'valid_until', 'notes', 'is_expired_display')

    def is_expired_display(self, obj):
        return obj.is_expired()
    is_expired_display.boolean = True
    is_expired_display.short_description = "Expired?"

# =====================================================
# Instrument Admin
# =====================================================
class InstrumentAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'serial_number', 'treatment_plant', 'phase', 'protocol',
        'status_colored', 'last_seen', 'health_indicator', 'is_active'
    )
    list_filter = ('status', 'protocol', 'is_active', 'treatment_plant', 'phase')
    search_fields = ('name', 'serial_number', 'ip_address', 'mac_address')
    readonly_fields = ('last_seen',)
    ordering = ('treatment_plant', 'name')
    inlines = [SensorInline, CalibrationInline]

    def status_colored(self, obj):
        return colored_status(obj.status)
    status_colored.admin_order_field = 'status'
    status_colored.short_description = 'Status'

    def health_indicator(self, obj):
        if obj.last_seen:
            age_sec = (now() - obj.last_seen).total_seconds()
            if age_sec > obj.expected_heartbeat_sec * 3:
                color, text = 'orange', 'STALE'
            else:
                color, text = 'green', 'HEALTHY'
        else:
            color, text = 'red', 'UNKNOWN'
        return format_html('<span style="color: {}; font-weight:bold;">{}</span>', color, text)
    health_indicator.short_description = 'Health'

# =====================================================
# Sensor Admin
# =====================================================
class SensorAdmin(admin.ModelAdmin):
    list_display = ('name', 'instrument', 'parameter', 'stage', 'unit', 'is_primary', 'is_active', 'treatment_plant', 'phase', 'sensor_health')
    list_filter = ('stage', 'is_primary', 'is_active', 'treatment_plant', 'phase')
    search_fields = ('name', 'instrument__name', 'parameter__name')
    readonly_fields = ('treatment_plant', 'phase')
    ordering = ('instrument', 'stage')

    def sensor_health(self, obj):
        latest = obj.health_snapshots.order_by('-assessed_at').first()
        score = latest.health_score if latest else 0
        return health_badge(score)
    sensor_health.short_description = 'Health'

# =====================================================
# OnlineMeasurement Admin
# =====================================================
class OnlineMeasurementAdmin(admin.ModelAdmin):
    list_display = ('sensor', 'value', 'unit_display', 'measured_at', 'quality_flag', 'treatment_plant', 'phase')
    list_filter = ('quality_flag', 'sensor__stage', 'treatment_plant', 'phase')
    search_fields = ('sensor__name',)
    readonly_fields = ('treatment_plant', 'phase')
    date_hierarchy = 'measured_at'
    ordering = ('-measured_at',)

    def unit_display(self, obj):
        return obj.sensor.unit
    unit_display.short_description = 'Unit'

# =====================================================
# DerivedMetric Admin
# =====================================================
class DerivedMetricAdmin(admin.ModelAdmin):
    list_display = ('sensor', 'metric_type', 'value', 'window_start', 'window_end', 'treatment_plant', 'phase')
    list_filter = ('metric_type', 'sensor__stage', 'treatment_plant', 'phase')
    search_fields = ('sensor__name',)
    readonly_fields = ('treatment_plant', 'phase')
    date_hierarchy = 'window_end'
    ordering = ('-window_end',)

# =====================================================
# SensorHealthSnapshot Admin
# =====================================================
class SensorHealthSnapshotAdmin(admin.ModelAdmin):
    list_display = ('sensor', 'health_score', 'assessed_at', 'reason')
    list_filter = ('sensor__instrument',)
    search_fields = ('sensor__name', 'sensor__instrument__name')
    readonly_fields = ('assessed_at',)
    date_hierarchy = 'assessed_at'
    ordering = ('-assessed_at',)

# =====================================================
# SCADA Real-Time Dashboard Admin
# =====================================================
class SCADADashboardAdmin(InstrumentAdmin):
    change_list_template = "instruments/scada_dashboard.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "scada-dashboard/",
                self.admin_site.admin_view(self.scada_dashboard_view),
                name="scada-dashboard",
            ),
        ]
        return custom_urls + urls

    def scada_dashboard_view(self, request):
        instruments = Instrument.objects.prefetch_related('sensors', 'phase').all()
        dashboard_data = {}

        for instr in instruments:
            phase_name = instr.phase.name if instr.phase else "No Phase"
            if phase_name not in dashboard_data:
                dashboard_data[phase_name] = {"sensors": [], "avg_health": 0, "count": 0}

            for sensor in instr.sensors.all():
                latest_snapshot = sensor.health_snapshots.order_by('-assessed_at').first()
                health_score = float(latest_snapshot.health_score) if latest_snapshot else 0.5
                status = sensor.instrument.status if sensor.instrument else 'offline'

                # Color coding
                if status == 'online' and health_score > 0.7:
                    color = 'green'
                elif status == 'degraded' or health_score <= 0.7:
                    color = 'yellow'
                else:
                    color = 'red'

                dashboard_data[phase_name]["sensors"].append({
                    "uuid": str(sensor.uuid),
                    "name": sensor.name,
                    "parameter": sensor.parameter.name,
                    "status": status,
                    "health_score": health_score,
                    "color": color
                })
                dashboard_data[phase_name]["avg_health"] += health_score
                dashboard_data[phase_name]["count"] += 1

        # Average health per phase
        for phase, pdata in dashboard_data.items():
            pdata["avg_health"] = pdata["avg_health"] / pdata["count"] if pdata["count"] > 0 else 0

        context = dict(
            self.admin_site.each_context(request),
            dashboard_json=json.dumps(dashboard_data)
        )
        return TemplateResponse(request, "instruments/scada_dashboard.html", context)

# =====================================================
# Safe Registration Utility
# =====================================================
def safe_register(model, admin_class=None):
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass
    admin.site.register(model, admin_class) if admin_class else admin.site.register(model)

# =====================================================
# Register all models
# =====================================================
safe_register(Instrument, SCADADashboardAdmin)
safe_register(Sensor, SensorAdmin)
safe_register(OnlineMeasurement, OnlineMeasurementAdmin)
safe_register(DerivedMetric, DerivedMetricAdmin)
safe_register(InstrumentCalibration)  # default admin
safe_register(SensorHealthSnapshot, SensorHealthSnapshotAdmin)
