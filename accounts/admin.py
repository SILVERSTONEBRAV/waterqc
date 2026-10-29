# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from django.http import HttpResponseRedirect
from django.urls import reverse

from core.models import Section, SystemConfiguration, AuditLogEntry, IPRestriction, UserSession
from .models import CustomUser
from django.contrib.auth.models import Group, Permission


# ============================================
# Section Admin
# ============================================
@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "treatment_plant", "is_active")
    list_filter = ("treatment_plant", "is_active")
    search_fields = ("code", "name", "treatment_plant__name")
    ordering = ("treatment_plant", "name")
    actions = ["activate_sections", "deactivate_sections"]

    @admin.action(description="Activate selected sections")
    def activate_sections(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} sections activated.")

    @admin.action(description="Deactivate selected sections")
    def deactivate_sections(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} sections deactivated.")


# ============================================
# System Configuration Admin (Singleton)
# ============================================
@admin.register(SystemConfiguration)
class SystemConfigurationAdmin(admin.ModelAdmin):
    save_on_top = True
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("⚠️ Singleton Warning", {
            "fields": (),
            "description": mark_safe(
                '<div style="padding:10px;background:#f39c12;color:white;border-radius:5px;">'
                '⚠️ Singleton configuration. Editing here affects the entire system.'
                '</div>'
            )
        }),
        ("Password Policy", {
            "classes": ("collapse",),
            "fields": (
                "password_min_length",
                "password_require_digit",
                "password_require_uppercase",
                "password_require_lowercase",
                "password_require_special",
                "password_history_count",
                "password_expire_days",
            ),
        }),
        ("Cache Policy", {"classes": ("collapse",), "fields": ("cache_timeout_seconds",)}),
        ("Security / MFA", {
            "classes": ("collapse",),
            "fields": (
                "adaptive_mfa_enabled",
                "adaptive_risk_threshold",
                "require_2fa_for_high_risk",
            ),
        }),
        ("Audit / Logging", {
            "classes": ("collapse",),
            "fields": (
                "audit_log_retention_days",
                "log_data_exports",
                "log_anomalies",
            ),
        }),
        ("Identity Rules", {
            "classes": ("collapse",),
            "fields": (
                "email_domain",
                "pf_prefix",
                "pf_length",
                "mobile_number_regex",
            ),
        }),
        ("Timestamps", {"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = SystemConfiguration.current()
        return HttpResponseRedirect(
            reverse("admin:core_systemconfiguration_change", args=[obj.pk])
        )


# ============================================
# Custom User Admin
# ============================================
@admin.register(CustomUser)
class CustomUserAdmin(DjangoUserAdmin):
    model = CustomUser

    ordering = ("username",)

    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "mobile_number",
    )

    list_display = (
        "username",
        "full_name",
        "email",
        "is_active",
        "is_staff",
        "is_superuser",
        "is_locked",
        "mfa_enabled",
        "risk_status",
        "section",
        "assigned_treatment_plant",
        "assigned_lab",
        "password_status",
        "group_summary",
        "last_login",
    )

    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "is_locked",
        "mfa_enabled",
        "section",
        "groups",
        "assigned_treatment_plant",
        "assigned_lab",
    )

    filter_horizontal = (
        "groups",
        "user_permissions",
    )

    readonly_fields = (
        "system_config_summary",
        "date_joined",
        "last_login",
        "password_last_set",
        "failed_login_attempts",
        "deactivated_at",
        "profile_picture_preview",
        "active_session_count",
        "risk_status",
        "group_redirect_preview",
    )

    class Media:
        js = ("core/js/plant_section_user_cascade.js",)

    fieldsets = (

        (
            "System-wide Configuration (Read Only)",
            {
                "fields": (
                    "system_config_summary",
                ),
                "description":
                    "Reference system-wide constraints while editing users.",
            }
        ),

        (
            "Account Information",
            {
                "fields": (
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "section",
                )
            }
        ),

        (
            "Authentication & Access",
            {
                "classes": ("collapse",),
                "fields": (
                    "password",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                    "group_redirect_preview",
                )
            }
        ),

        (
            "Security",
            {
                "classes": ("collapse",),
                "fields": (
                    "password_last_set",
                    "is_locked",
                    "failed_login_attempts",
                    "active_session_count",
                    "risk_status",
                    "mfa_enabled",
                    "mfa_secret",
                )
            }
        ),

        (
            "Assignments",
            {
                "classes": ("collapse",),
                "fields": (
                    "assigned_treatment_plant",
                    "assigned_lab",
                )
            }
        ),

        (
            "Contact & Profile",
            {
                "classes": ("collapse",),
                "fields": (
                    "mobile_number",
                    "profile_picture",
                    "profile_picture_preview",
                )
            }
        ),

        (
            "Lifecycle",
            {
                "classes": ("collapse",),
                "fields": (
                    "date_joined",
                    "last_login",
                    "deactivated_at",
                )
            }
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "mobile_number",
                    "section",
                    "assigned_treatment_plant",
                    "assigned_lab",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                ),
            },
        ),
    )

    actions = (
        "activate_users",
        "deactivate_users",
        "unlock_users",
        "lock_users",
        "grant_superuser",
        "revoke_superuser",
    )

    # ============================================
    # DISPLAY HELPERS
    # ============================================

    def full_name(self, obj):
        return (
            f"{obj.first_name} {obj.last_name}"
        ).strip() or "-"

    full_name.short_description = "Full Name"

    def group_summary(self, obj):
        groups = list(
            obj.groups.values_list(
                "name",
                flat=True,
            )
        )

        if not groups:
            return mark_safe(
                '<span style="color:red;font-weight:bold;">No Groups</span>'
            )

        return ", ".join(groups)

    group_summary.short_description = "Groups"

    def system_config_summary(self, obj=None):
        config = SystemConfiguration.current()

        html = f"""
        <div style="padding:12px;background:#fafafa;border:1px solid #ddd;border-radius:6px;line-height:1.8;">
            <strong>Password Policy</strong><br>
            Min Length: {config.password_min_length} |
            Digit: {config.password_require_digit} |
            Uppercase: {config.password_require_uppercase} |
            Lowercase: {config.password_require_lowercase} |
            Special: {config.password_require_special} |
            Expiry: {config.password_expire_days} days
            <hr>

            <strong>Session Policy</strong><br>
            Automatic logouts: Disabled |
            Concurrent sessions: Allowed
            <hr>

            <strong>Security</strong><br>
            Adaptive MFA: {config.adaptive_mfa_enabled} |
            Require 2FA High Risk: {config.require_2fa_for_high_risk}
            <hr>

            <strong>Audit</strong><br>
            Retention: {config.audit_log_retention_days} days |
            Log Exports: {config.log_data_exports} |
            Log Anomalies: {config.log_anomalies}
        </div>
        """

        return mark_safe(html)

    system_config_summary.short_description = (
        "System Configuration Reference"
    )

    def active_session_count(self, obj):
        return UserSession.objects.filter(
            user=obj,
            terminated=False,
        ).count()

    active_session_count.short_description = (
        "Active Sessions"
    )

    def password_status(self, obj):
        if (
            hasattr(obj, "is_password_expired")
            and obj.is_password_expired()
        ):
            return mark_safe(
                '<span style="color:red;font-weight:bold;">Expired</span>'
            )

        return mark_safe(
            '<span style="color:green;font-weight:bold;">Valid</span>'
        )

    password_status.short_description = (
        "Password Status"
    )

    def risk_status(self, obj):
        failed = (
            getattr(obj, "failed_login_attempts", 0)
            or 0
        )

        if (
            getattr(obj, "is_locked", False)
            or failed >= 5
            or (
                hasattr(obj, "is_password_expired")
                and obj.is_password_expired()
            )
        ):
            return mark_safe(
                '<span style="color:red;font-weight:bold;">High Risk</span>'
            )

        return mark_safe(
            '<span style="color:green;font-weight:bold;">Low Risk</span>'
        )

    risk_status.short_description = "Risk Status"

    def profile_picture_preview(self, obj):

        if getattr(obj, "profile_picture", None):
            return mark_safe(
                f'''
                <img
                    src="{obj.profile_picture.url}"
                    style="
                        height:70px;
                        width:70px;
                        border-radius:8px;
                        object-fit:cover;
                        border:1px solid #ddd;
                    "
                />
                '''
            )

        return "(No picture)"

    profile_picture_preview.short_description = (
        "Profile Picture"
    )

    def group_redirect_preview(self, obj):

        from django.conf import settings

        group_map = getattr(
            settings,
            "LOGIN_GROUP_REDIRECT_MAP",
            {},
        ) or {}

        normalized = {
            str(k).upper().strip(): v
            for k, v in group_map.items()
        }

        groups = [
            g.upper().strip()
            for g in obj.groups.values_list(
                "name",
                flat=True,
            )
            if g
        ]

        if obj.is_superuser:
            return mark_safe(
                '<span style="color:#1e88e5;font-weight:bold;">Superuser Access</span>'
            )

        for group in groups:

            target = normalized.get(group)

            if target:
                return mark_safe(
                    f'''
                    <span style="color:green;font-weight:bold;">
                        {group} → {target}
                    </span>
                    '''
                )

        return mark_safe(
            '''
            <span style="color:red;font-weight:bold;">
                No dashboard redirect configured.
                User cannot login into assigned workspace.
            </span>
            '''
        )

    group_redirect_preview.short_description = (
        "Dashboard Assignment"
    )

    # ============================================
    # ACTIONS
    # ============================================

    @admin.action(
        description="Activate selected users"
    )
    def activate_users(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            is_active=True,
            deactivated_at=None,
        )

        self.message_user(
            request,
            f"{updated} users activated.",
        )

    @admin.action(
        description="Deactivate selected users"
    )
    def deactivate_users(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            is_active=False,
            deactivated_at=now(),
        )

        self.message_user(
            request,
            f"{updated} users deactivated.",
        )

    @admin.action(
        description="Unlock selected users"
    )
    def unlock_users(
        self,
        request,
        queryset,
    ):
        for user in queryset:
            if hasattr(user, "unlock_account"):
                user.unlock_account()

        self.message_user(
            request,
            f"{queryset.count()} users unlocked.",
        )

    @admin.action(
        description="Lock selected users"
    )
    def lock_users(
        self,
        request,
        queryset,
    ):
        for user in queryset:
            if hasattr(user, "lock_account"):
                user.lock_account()

        self.message_user(
            request,
            f"{queryset.count()} users locked.",
        )

    @admin.action(
        description="Grant superuser access"
    )
    def grant_superuser(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            is_superuser=True,
            is_staff=True,
        )

        self.message_user(
            request,
            f"{updated} users granted superuser access.",
        )

    @admin.action(
        description="Revoke superuser access"
    )
    def revoke_superuser(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            is_superuser=False,
        )

        self.message_user(
            request,
            f"{updated} users had superuser access revoked.",
        )

    # ============================================
    # SAVE OVERRIDES
    # ============================================

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):

        if obj.username:
            obj.username = (
                obj.username.upper().strip()
            )

        super().save_model(
            request,
            obj,
            form,
            change,
        )

    @admin.action(description="Activate selected users")
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True, deactivated_at=None)
        self.message_user(request, f"{updated} users activated.")

    @admin.action(description="Deactivate selected users")
    def deactivate_users(self, request, queryset):
        updated = queryset.update(is_active=False, deactivated_at=now())
        self.message_user(request, f"{updated} users deactivated.")

    @admin.action(description="Unlock selected users")
    def unlock_users(self, request, queryset):
        for user in queryset:
            user.unlock_account()
        self.message_user(request, f"{queryset.count()} users unlocked.")

    @admin.action(description="Lock selected users")
    def lock_users(self, request, queryset):
        for user in queryset:
            user.lock_account()
        self.message_user(request, f"{queryset.count()} users locked.")

    def save_model(self, request, obj, form, change):
        if obj.username:
            obj.username = obj.username.upper()
        super().save_model(request, obj, form, change)


# ============================================
# Audit Log Admin
# ============================================
@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "action", "model_name", "object_id", "description")
    list_filter = ("action", "model_name")
    search_fields = ("description", "object_id", "model_name")
    readonly_fields = ("action", "model_name", "object_id", "description", "timestamp", "ip_address", "user_agent")
    ordering = ("-timestamp",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================
# IP Restriction Admin
# ============================================
@admin.register(IPRestriction)
class IPRestrictionAdmin(admin.ModelAdmin):
    list_display = ("name", "ip_range_start", "ip_range_end", "description")
    search_fields = ("name", "description")
    ordering = ("name",)


# ============================================
# User Session Admin
# ============================================
@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = (
        "user", "session_key", "login_time", "last_activity", "terminated", "mfa_enabled", "failed_login_attempts")
    list_filter = ("terminated",)
    search_fields = ("user__username", "session_key")
    readonly_fields = (
        "user", "session_key", "login_time", "last_activity", "terminated", "mfa_enabled", "failed_login_attempts")
    ordering = ("-login_time",)
    actions = ["terminate_sessions"]

    def mfa_enabled(self, obj):
        return obj.user.mfa_enabled

    mfa_enabled.boolean = True
    mfa_enabled.short_description = "MFA Enabled"

    def failed_login_attempts(self, obj):
        return obj.user.failed_login_attempts

    failed_login_attempts.short_description = "Failed Logins"

    @admin.action(description="Terminate selected sessions")
    def terminate_sessions(self, request, queryset):
        updated = queryset.update(terminated=True)
        self.message_user(request, f"{updated} sessions terminated.")


# ============================================
# Group Dashboard Redirect Admin
# ============================================
from core.models import GroupDashboardRedirect
from django.contrib.auth.models import Group


@admin.register(GroupDashboardRedirect)
class GroupDashboardRedirectAdmin(admin.ModelAdmin):
    """
    Admin for managing which dashboard each auth group lands on after login.
    These entries override the LOGIN_GROUP_REDIRECT_MAP setting at runtime.
    """

    list_display = (
        "group_name",
        "redirect_url",
        "label",
        "is_active",
        "priority",
        "resolved_url_preview",
        "updated_at",
    )
    list_display_links = ("group_name", "redirect_url")
    list_filter = ("is_active",)
    search_fields = ("group__name", "redirect_url", "label")
    ordering = ("priority", "group__name")
    list_editable = ("is_active", "priority")
    readonly_fields = ("created_at", "updated_at", "resolved_url_preview", "cache_status_info")
    autocomplete_fields = ("group",)
    save_on_top = True

    fieldsets = (
        (
            "🗺️ Redirect Mapping",
            {
                "fields": ("group", "redirect_url", "label", "is_active", "priority"),
                "description": mark_safe(
                    '<div style="padding:10px 14px;background:linear-gradient(135deg,#0f172a,#1e3a5f);'
                    'color:#38bdf8;border-radius:8px;border:1px solid #38bdf840;margin-bottom:10px;">'
                    '<strong>🔑 Group → Dashboard Mapping</strong><br>'
                    'Assign a post-login destination URL to each auth group. '
                    'DB entries <strong>override</strong> the settings-level '
                    '<code>LOGIN_GROUP_REDIRECT_MAP</code>. '
                    'When a user belongs to multiple groups, the <em>lowest priority number</em> wins.'
                    '</div>'
                ),
            },
        ),
        (
            "📊 Resolution Preview",
            {
                "classes": ("collapse",),
                "fields": ("resolved_url_preview", "cache_status_info"),
            },
        ),
        (
            "🕒 Timestamps",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    actions = ["activate_redirects", "deactivate_redirects", "test_resolve_urls", "flush_redirect_cache"]

    # ---- column displays ----

    def group_name(self, obj):
        return mark_safe(
            f'<strong style="color:#38bdf8">{obj.group.name}</strong>'
        )
    group_name.short_description = "Group"
    group_name.admin_order_field = "group__name"

    def resolved_url_preview(self, obj):
        from django.shortcuts import resolve_url
        from django.urls import NoReverseMatch
        url = (obj.redirect_url or "").strip()
        if not url:
            return mark_safe('<span style="color:#ef4444">⚠ No URL</span>')
        try:
            resolved = resolve_url(url) if not url.startswith("/") else url
            return mark_safe(
                f'<a href="{resolved}" target="_blank" '
                f'style="color:#22c55e;font-weight:600;">'
                f'✓ {resolved}</a>'
            )
        except (NoReverseMatch, Exception) as exc:
            return mark_safe(
                f'<span style="color:#f59e0b">⚠ Cannot resolve: {exc}</span>'
            )
    resolved_url_preview.short_description = "Resolved URL"

    def cache_status_info(self, obj):
        from django.core.cache import cache
        cached = cache.get("gdr:redirect_map")
        if cached is None:
            return mark_safe('<span style="color:#94a3b8">Cache: COLD (will be populated on next login)</span>')
        group_key = (obj.group.name or "").strip().upper()
        if group_key in cached:
            return mark_safe(
                f'<span style="color:#22c55e">✓ Cache HOT — group "{obj.group.name}" → {cached[group_key]}</span>'
            )
        return mark_safe(
            f'<span style="color:#f59e0b">⚠ Cache HOT but group "{obj.group.name}" not present (inactive or overridden)</span>'
        )
    cache_status_info.short_description = "Live Cache Status"

    # ---- actions ----

    @admin.action(description="✅ Activate selected redirects")
    def activate_redirects(self, request, queryset):
        updated = queryset.update(is_active=True)
        from django.core.cache import cache
        cache.delete("gdr:redirect_map")
        self.message_user(request, f"{updated} redirect(s) activated. Cache cleared.")

    @admin.action(description="🚫 Deactivate selected redirects")
    def deactivate_redirects(self, request, queryset):
        updated = queryset.update(is_active=False)
        from django.core.cache import cache
        cache.delete("gdr:redirect_map")
        self.message_user(request, f"{updated} redirect(s) deactivated. Cache cleared.")

    @admin.action(description="🔍 Test-resolve selected redirect URLs")
    def test_resolve_urls(self, request, queryset):
        from django.shortcuts import resolve_url
        from django.urls import NoReverseMatch
        results = []
        for obj in queryset:
            url = (obj.redirect_url or "").strip()
            try:
                resolved = resolve_url(url) if not url.startswith("/") else url
                results.append(f"✓ {obj.group.name} → {resolved}")
            except (NoReverseMatch, Exception) as exc:
                results.append(f"✗ {obj.group.name}: {exc}")
        self.message_user(request, " | ".join(results))

    @admin.action(description="🔄 Flush redirect cache")
    def flush_redirect_cache(self, request, queryset):
        from django.core.cache import cache
        cache.delete("gdr:redirect_map")
        self.message_user(request, "Redirect cache flushed. Next login will reload from DB.")

