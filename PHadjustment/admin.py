from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.shortcuts import redirect
from .models import PHAdjustmentTest, PHAdjustmentJarResult


# ================================
# 🧠 Smart List Filter for Reviews
# ================================
class ReviewStatusFilter(admin.SimpleListFilter):
    title = "Review Stage"
    parameter_name = "review_status"

    def lookups(self, request, model_admin):
        return [
            ('pending', '🔴 Pending'),
            ('verified', '🔵 Verified'),
            ('confirmed', '🟠 Confirmed'),
            ('approved', '🟢 Approved'),
        ]

    def queryset(self, request, queryset):
        v, c, a = 'verified_at', 'confirmed_at', 'approved_at'
        match self.value():
            case 'pending': return queryset.filter(**{f'{v}__isnull': True})
            case 'verified': return queryset.filter(**{f'{v}__isnull': False, f'{c}__isnull': True})
            case 'confirmed': return queryset.filter(**{f'{c}__isnull': False, f'{a}__isnull': True})
            case 'approved': return queryset.filter(**{f'{a}__isnull': False})


# =============================
# 📊 Inline Jar Results Display
# =============================
class PHAdjustmentJarResultInline(admin.TabularInline):
    model = PHAdjustmentJarResult
    extra = 0
    readonly_fields = ['performance_rank', 'is_optimal', 'created_at']
    fields = ('jar_number', 'dosage_ml', 'resulting_ph', 'performance_rank', 'is_optimal')
    ordering = ['jar_number']

    def has_add_permission(self, request, obj=None):
        return False  # Disable inline adding for safety


# ====================================
# 🧭 Smart Actions for Workflow Control
# ====================================
def create_workflow_action(stage):
    def action(modeladmin, request, queryset):
        for obj in queryset:
            try:
                getattr(obj, stage)(request.user)
                obj.save()
                messages.success(request, f"{stage.capitalize()} success: {obj}")
            except Exception as e:
                messages.error(request, f"{stage.capitalize()} error for {obj}: {e}")
    action.__name__ = f"action_{stage}"
    action.short_description = f"Mark selected as {stage}"
    return action

verify_tests = create_workflow_action('verify')
confirm_tests = create_workflow_action('confirm')
approve_tests = create_workflow_action('approve')


# ====================================
# 🛠️ Auto-generate 6 Jars from Source
# ====================================
def auto_generate_jars(modeladmin, request, queryset):
    for test in queryset:
        if test.results.exists():
            messages.warning(request, f"{test} already has jars, skipping.")
            continue
        try:
            test.prefill_jars_from_source()
            messages.success(request, f"Successfully created 6 jars for {test}.")
        except Exception as e:
            messages.error(request, f"Error generating jars for {test}: {e}")
auto_generate_jars.short_description = "Auto-generate 6 jars from source JarTest"


# ====================================
# 🧬 Main Admin for PH Adjustment Test
# ====================================
@admin.register(PHAdjustmentTest)
class PHAdjustmentTestAdmin(admin.ModelAdmin):
    list_display = (
        'test_date', 'treatment_plant', 'analyst', 'established_dosage_display',
        'review_stage_badge', 'quick_jump', 'sparkline_preview', 'generate_jars_button'
    )
    list_filter = ['treatment_plant', ReviewStatusFilter]
    search_fields = ['remarks', 'analyst__full_name', 'treatment_plant__name']
    readonly_fields = (
        'established_dosage_ml', 'verified_by', 'verified_at',
        'confirmed_by', 'confirmed_at', 'approved_by', 'approved_at',
        'created_at', 'sparkline_preview'
    )
    inlines = [PHAdjustmentJarResultInline]
    ordering = ['-test_date']
    actions = [verify_tests, confirm_tests, approve_tests, auto_generate_jars]

    fieldsets = (
        ("Test Info", {
            'fields': ('treatment_plant', 'test_date', 'analyst', 'remarks')
        }),
        ("Results Overview", {
            'fields': ('established_dosage_ml', 'sparkline_preview')
        }),
        ("Review Workflow", {
            'classes': ['collapse'],
            'fields': (
                ('verified_by', 'verified_at'),
                ('confirmed_by', 'confirmed_at'),
                ('approved_by', 'approved_at'),
            )
        }),
        ("System Info", {
            'classes': ['collapse'],
            'fields': ('created_at',)
        }),
    )

    def quick_jump(self, obj):
        url = reverse("admin:phadjustment_phadjustmenttest_change", args=[obj.pk])
        return format_html(f'<a href="{url}">🧭 View/Edit</a>')
    quick_jump.short_description = "Actions"

    def sparkline_preview(self, obj):
        if not obj.pk:
            return "-"
        jars = obj.results.order_by('jar_number').all()
        if not jars:
            return "No jars"

        labels = [f"J{j.jar_number}" for j in jars]
        values = [j.resulting_ph or 0 for j in jars]
        dots = "".join(f"<span title='{l}: pH {v}' style='color:#00bcd4;'>&#9679;</span>" for l, v in zip(labels, values))
        return mark_safe(f"<div style='font-size: 1.2em;'>{dots}</div>")
    sparkline_preview.short_description = "pH Overview"

    def review_stage_badge(self, obj):
        if obj.approved_at:
            return format_html('<span style="color:green;font-weight:600;">🟢 Approved</span>')
        if obj.confirmed_at:
            return format_html('<span style="color:orange;">🟠 Confirmed</span>')
        if obj.verified_at:
            return format_html('<span style="color:blue;">🔵 Verified</span>')
        return format_html('<span style="color:red;">🔴 Pending</span>')
    review_stage_badge.short_description = "Status"

    def established_dosage_display(self, obj):
        return f"{obj.established_dosage_ml} mL" if obj.established_dosage_ml else "—"
    established_dosage_display.short_description = "Dosage"

    # ====================================
    # ⚡ Auto-generate button in list view
    # ====================================
    def generate_jars_button(self, obj):
        if obj.results.exists():
            return "✅ Jars already generated"
        url = reverse('admin:phadjustment_phadjustmenttest_changelist') + f"?generate_jars={obj.pk}"
        return format_html(f'<a class="button" href="{url}">⚡ Generate 6 Jars</a>')
    generate_jars_button.short_description = "Auto-generate Jars"
    generate_jars_button.allow_tags = True

    # Handle one-click URL in changelist
    def changelist_view(self, request, extra_context=None):
        if 'generate_jars' in request.GET:
            pk = request.GET['generate_jars']
            test = PHAdjustmentTest.objects.filter(pk=pk).first()
            if test:
                if test.results.exists():
                    self.message_user(request, f"{test} already has jars.", level=messages.WARNING)
                else:
                    try:
                        test.prefill_jars_from_source()
                        self.message_user(request, f"Successfully created 6 jars for {test}.", level=messages.SUCCESS)
                    except Exception as e:
                        self.message_user(request, f"Error generating jars for {test}: {e}", level=messages.ERROR)
            return redirect(request.path)
        return super().changelist_view(request, extra_context=extra_context)


# ========================================
# 📦 Jar Results Admin (Fallback Register)
# ========================================
@admin.register(PHAdjustmentJarResult)
class PHAdjustmentJarResultAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'jar_number', 'dosage_ml', 'resulting_ph', 'performance_rank', 'is_optimal')
    list_filter = ['jar_number', 'is_optimal']
    search_fields = ['test__treatment_plant__name']
    readonly_fields = ['performance_rank', 'is_optimal', 'created_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("test")
