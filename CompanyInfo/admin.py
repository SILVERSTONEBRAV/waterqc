# company/admin.py
import nested_admin
from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.utils.safestring import SafeString

from .models import CompanyInfo, RegionalInfo, ZonalInfo, SubZonalInfo

# =====================================================
# 🔹 Helper: Dynamic Company Branding
# =====================================================
def _get_company() -> CompanyInfo | None:
    try:
        return CompanyInfo.objects.first()
    except Exception:
        return None


def _apply_dynamic_branding():
    """Set admin header, title, and index dynamically from CompanyInfo."""
    company = _get_company()
    admin.site.site_header = company.name if company and company.name else "NCWSCwaterLAB"
    admin.site.site_title = company.slug if company and company.slug else "NCWSCwaterLAB"
    admin.site.index_title = "Admin Panel"


_apply_dynamic_branding()

# =====================================================
# 🎨 Custom Admin Context with Logo & Styling
# =====================================================
_original_each_context = admin.site.each_context


def _custom_each_context(request) -> dict:
    context = _original_each_context(request)
    company = _get_company()

    # Dynamic header with logo and responsive styling
    logo_html = (
        f"<img src='{company.logo.url}' style='height:42px;width:auto;border-radius:4px;object-fit:contain;'/>"
        if company and company.logo
        else ""
    )

    company_name = company.name if company else "NCWSCwaterLAB"

    context["site_header"] = mark_safe(
        f"""
        <div style="
            display:flex;
            align-items:center;
            gap:12px;
            width:100%;
            padding:8px 16px;
            background: linear-gradient(90deg, #1f2937, #3b4a5a);
            border-radius:8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.25);
            font-family:'Segoe UI', Roboto, Arial, sans-serif;
            transition: background 0.3s ease;
        ">
            {logo_html}
            <span style="
                font-weight:700;
                color:#ffffff;
                font-size:1.2rem;
                white-space:nowrap;
                text-overflow:ellipsis;
                overflow:hidden;
            ">
                {company_name}
            </span>
        </div>
        """
    )

    # Scoped admin CSS for advanced styling
    context["inline_admin_css"] = mark_safe(
        """
        <style>
            /* Admin header enhancements */
            #header {
                background-color: transparent !important;
                border-bottom: none !important;
            }

            #header h1, #header a, #user-tools a {
                color: #ffffff !important;
                font-weight: 700 !important;
            }

            /* Hover & transition for links */
            #header a:hover, #user-tools a:hover {
                color: #ffcc00 !important;
                transition: color 0.2s ease;
            }

            /* Make nested inline tables more readable */
            .nested-inline {
                background: #f9fafb;
                border: 1px solid #d1d5db;
                padding: 8px;
                border-radius: 4px;
                margin-bottom: 12px;
            }

            /* Sticky admin header for scroll */
            #header {
                position: sticky;
                top: 0;
                z-index: 999;
            }
        </style>
        """
    )
    return context


admin.site.each_context = _custom_each_context

# =====================================================
# 🔹 Nested Inlines
# =====================================================
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
