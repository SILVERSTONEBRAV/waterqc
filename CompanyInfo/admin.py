# company/admin.py
import nested_admin
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import SafeString

from .models import CompanyInfo, RegionalInfo, ZonalInfo, SubZonalInfo

# Keep admin metadata text-only. The branded template reads the current company
# and logo from CompanyInfo.context_processors.company_context.
admin.site.site_header = "Water Quality Management"
admin.site.site_title = "NCWSC Administration"
admin.site.index_title = "Operations Console"


class SubZonalInfoInline(nested_admin.NestedTabularInline):
    model = SubZonalInfo
    extra = 1
    readonly_fields = ("slug",)
    fields = ("name", "slug", "address", "coordinates", "boundary")
    classes = ("nested-inline",)


class ZonalInfoInline(nested_admin.NestedTabularInline):
    model = ZonalInfo
    extra = 1
    readonly_fields = ("slug",)
    fields = ("name", "slug", "address", "coordinates", "boundary")
    inlines = [SubZonalInfoInline]
    classes = ("nested-inline",)


class RegionalInfoInline(nested_admin.NestedTabularInline):
    model = RegionalInfo
    extra = 1
    readonly_fields = ("slug",)
    fields = (
        "name",
        "slug",
        "address",
        "office_location",
        "telephone_number",
        "coordinates",
        "boundary",
    )
    inlines = [ZonalInfoInline]
    classes = ("nested-inline",)

# =====================================================
# 🏢 Company Admin
# =====================================================
@admin.register(CompanyInfo)
class CompanyInfoAdmin(nested_admin.NestedModelAdmin):
    list_display = (
        "name",
        "address",
        "location",
        "phone_number",
        "telephone",
        "motto",
        'favicon',
        "logo_preview",
    )
    search_fields = ("name", "address", "location", "phone_number")
    readonly_fields = ("slug", "logo_preview")
    inlines = [RegionalInfoInline]
    ordering = ("name",)

    def logo_preview(self, obj) -> SafeString:
        if obj.logo:
            return format_html(
                "<img src='{}' style='height:50px;border-radius:6px;object-fit:contain;'/>",
                obj.logo.url,
            )
        return "—"

    logo_preview.short_description = "Logo"
