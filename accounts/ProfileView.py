# accounts/ProfileView.py

import django
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import (
    Group,
    Permission,
)
from django.contrib.sessions.models import Session
from django.db.models import (
    Count,
    Q,
)
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    TemplateView,
    UpdateView,
    ListView,
    CreateView,
    DeleteView,
    DetailView,
    View,
)
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.forms import (
    CustomUserForm,
    ProfilePictureForm,
    SectionForm,
)
from accounts.models import (
    CustomUser,
    audit_user_event,
)

from core.mixins import WanjalaMixin
from core.models import (
    Section,
    SystemConfiguration,
    AuditLogEntry,
    IPRestriction,
    UserSession,
    UserPasswordHistory,
)


# ==========================================================
# ADMIN MIXIN
# ==========================================================
class SuperUserRequiredMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        return self.request.user.is_superuser


# ==========================================================
# DASHBOARD
# ==========================================================
class ProfileView(
    WanjalaMixin,
    TemplateView,
):
    template_name = "accounts/dashboard.html"

    def get_users_queryset(self):
        qs = (
            CustomUser.objects
            .select_related("section")
            .prefetch_related(
                "groups",
                "user_permissions",
            )
        )

        q = self.request.GET.get("search")

        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )

        status = self.request.GET.get("status")

        filters = {
            "active": {"is_active": True},
            "inactive": {"is_active": False},
            "locked": {"is_locked": True},
            "staff": {"is_staff": True},
            "mfa": {"mfa_enabled": True},
            "verified": {"email_verified": True},
            "superusers": {"is_superuser": True},
        }

        if status in filters:
            qs = qs.filter(**filters[status])

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user = self.request.user
        now = timezone.now()

        users = self.get_users_queryset()

        sections = (
            Section.objects
            .annotate(user_count=Count("users"))
            .order_by("name")
        )

        groups = (
            Group.objects
            .annotate(
                user_count=Count("accounts_users")
            )
            .order_by("name")
        )

        permissions = (
            Permission.objects
            .select_related("content_type")
            .order_by(
                "content_type__app_label",
                "codename",
            )
        )

        sessions = (
            Session.objects
            .filter(
                expire_date__gte=now
            )
            .order_by("-expire_date")
        )

        user_sessions = (
            UserSession.objects
            .select_related("user")
            .order_by("-login_time")
        )

        audit_logs = (
            AuditLogEntry.objects
            .all()[:100]
        )

        ip_restrictions = (
            IPRestriction.objects
            .all()
        )

        password_history = (
            UserPasswordHistory.objects
            .filter(user=user)
            .order_by("-created_at")
        )

        configuration = (
            SystemConfiguration.current()
        )

        expiry_days = (
            configuration.password_expire_days
            if configuration
            else 90
        )

        password_expiry = (
            user.password_last_set
            + timezone.timedelta(days=expiry_days)
            if user.password_last_set
            else None
        )

        profile_fields = {
            "Username": user.username,
            "Email": user.email,
            "First Name": user.first_name,
            "Last Name": user.last_name,
            "Mobile Number": user.mobile_number,
            "Section": user.section,
            "Date Joined": user.date_joined,
            "Last Login": user.last_login,
            "Password Last Set": user.password_last_set,
            "Password Expiry": password_expiry,
            "Failed Login Attempts": user.failed_login_attempts,
            "Email Verified": user.email_verified,
            "MFA Enabled": user.mfa_enabled,
            "Account Locked": user.is_locked,
            "Groups": ", ".join(
                user.groups.values_list(
                    "name",
                    flat=True,
                )
            ),
            "Permissions": ", ".join(
                user.user_permissions.values_list(
                    "codename",
                    flat=True,
                )
            ),
        }

        stats = {
            "total_users": users.count(),
            "active_users": users.filter(
                is_active=True
            ).count(),
            "inactive_users": users.filter(
                is_active=False
            ).count(),
            "locked_users": users.filter(
                is_locked=True
            ).count(),
            "verified_users": users.filter(
                email_verified=True
            ).count(),
            "mfa_users": users.filter(
                mfa_enabled=True
            ).count(),
            "staff_users": users.filter(
                is_staff=True
            ).count(),
            "superusers": users.filter(
                is_superuser=True
            ).count(),
            "total_groups": groups.count(),
            "total_sections": sections.count(),
            "total_permissions": permissions.count(),
            "active_sessions": sessions.count(),
            "tracked_sessions": user_sessions.count(),
            "audit_logs": audit_logs.count(),
            "ip_restrictions": ip_restrictions.count(),
        }

        system_info = {
            "django_version": django.get_version(),
            "debug": settings.DEBUG,
            "environment": (
                "Development"
                if settings.DEBUG
                else "Production"
            ),
            "server_time": now,
            "python_version": settings.PYTHON_VERSION
            if hasattr(settings, "PYTHON_VERSION")
            else None,
            "timezone": settings.TIME_ZONE,
            "installed_apps": len(
                settings.INSTALLED_APPS
            ),
        }

        context.update(
            {
                "user_obj": user,
                "users": users,
                "sections": sections,
                "groups": groups,
                "permissions": permissions,
                "sessions": sessions,
                "user_sessions": user_sessions,
                "audit_logs_list": audit_logs,
                "ip_restrictions_list": ip_restrictions,
                "password_history": password_history,
                "configuration": configuration,
                "fields": profile_fields,
                "recent_users": users.order_by(
                    "-date_joined"
                )[:10],
                "locked_accounts": users.filter(
                    is_locked=True
                )[:10],
                "inactive_accounts": users.filter(
                    is_active=False
                )[:10],
                "system_info": system_info,
                **stats,
            }
        )

        return context


# ==========================================================
# PROFILE PICTURE
# ==========================================================
class ProfilePictureUpdateView(
    WanjalaMixin,
    UpdateView,
):
    model = CustomUser
    form_class = ProfilePictureForm
    template_name = "accounts/profile/profile_picture_form.html"

    def get_object(self):
        return self.request.user

    def get_success_url(self):
        return reverse_lazy(
            "accounts:profile"
        )

    def form_valid(self, form):
        response = super().form_valid(form)

        audit_user_event(
            self.request.user,
            "PROFILE_PICTURE_UPDATED",
        )

        messages.success(
            self.request,
            "Profile picture updated successfully.",
        )

        return response


# ==========================================================
# USER VIEWS
# ==========================================================
class UserListView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    ListView,
):
    model = CustomUser
    template_name = "accounts/dashboard.html"
    context_object_name = "users"
    paginate_by = 50

    def get_queryset(self):
        return (
            CustomUser.objects
            .select_related("section")
            .prefetch_related(
                "groups",
                "user_permissions",
            )
        )


class UserCreateView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    CreateView,
):
    model = CustomUser
    form_class = CustomUserForm
    template_name = "accounts/profile/user_form.html"
    success_url = reverse_lazy(
        "accounts:profile"
    )

    def form_valid(self, form):
        response = super().form_valid(form)

        audit_user_event(
            self.request.user,
            f"USER_CREATED_{self.object.username}",
        )

        messages.success(
            self.request,
            "User created successfully.",
        )

        return response


class UserUpdateView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    UpdateView,
):
    model = CustomUser
    form_class = CustomUserForm
    template_name = "accounts/profile/user_form.html"
    success_url = reverse_lazy(
        "accounts:profile"
    )

    def form_valid(self, form):
        response = super().form_valid(form)

        audit_user_event(
            self.request.user,
            f"USER_UPDATED_{self.object.username}",
        )

        messages.success(
            self.request,
            "User updated successfully.",
        )

        return response


class UserDeleteView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    DeleteView,
):
    model = CustomUser
    template_name = "accounts/profile/user_confirm_delete.html"
    success_url = reverse_lazy(
        "accounts:profile"
    )

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()

        audit_user_event(
            request.user,
            f"USER_DELETED_{obj.username}",
        )

        messages.success(
            request,
            f"{obj.username} deleted successfully.",
        )

        return super().delete(
            request,
            *args,
            **kwargs,
        )


class UserDetailView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    DetailView,
):
    model = CustomUser
    template_name = "accounts/profile/user_detail.html"
    context_object_name = "user_obj"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        u = self.get_object()
        context["target_user"] = u
        context["user_fields"] = {
            "Username": u.username,
            "Full Name": (u.first_name + " " + u.last_name).strip() or u.username,
            "Email": u.email or "—",
            "Mobile Number": getattr(u, "mobile_number", "—") or "—",
            "Section": getattr(u.section, "name", "—") if getattr(u, "section", None) else "—",
            "Assigned Plant": str(getattr(u, "assigned_treatment_plant", "—") or "—"),
            "Assigned Lab": str(getattr(u, "assigned_lab", "—") or "—"),
            "Status": "Active" if u.is_active else "Inactive",
            "Role": "Superuser" if u.is_superuser else ("Staff" if u.is_staff else "Regular User"),
            "MFA Enabled": "Yes" if getattr(u, "mfa_enabled", False) else "No",
            "Date Joined": u.date_joined.strftime("%d %b %Y, %H:%M") if getattr(u, "date_joined", None) else "—",
            "Last Login": u.last_login.strftime("%d %b %Y, %H:%M") if getattr(u, "last_login", None) else "Never",
        }
        return context


# ==========================================================
# SUPPORTING LIST VIEWS
# ==========================================================
class SectionListView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    ListView,
):
    model = Section
    context_object_name = "sections"


class SectionCreateView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    CreateView,
):
    model = Section
    form_class = SectionForm
    template_name = "accounts/profile/section_form.html"
    success_url = reverse_lazy("accounts:profile")

    def get_template_names(self):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return ["accounts/partials/section_form_modal.html"]
        return [self.template_name]

    def form_valid(self, form):
        self.object = form.save()
        messages.success(
            self.request,
            f"Section '{self.object.name}' created successfully.",
        )
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return HttpResponse("SUCCESS")
        return super().form_valid(form)

    def form_invalid(self, form):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return render(
                self.request,
                "accounts/partials/section_form_modal.html",
                {
                    "form": form,
                    "action_url": self.request.path,
                },
            )
        return super().form_invalid(form)


class SectionUpdateView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    UpdateView,
):
    model = Section
    form_class = SectionForm
    template_name = "accounts/profile/section_form.html"
    success_url = reverse_lazy("accounts:profile")

    def get_template_names(self):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return ["accounts/partials/section_form_modal.html"]
        return [self.template_name]

    def form_valid(self, form):
        self.object = form.save()
        messages.success(
            self.request,
            f"Section '{self.object.name}' updated successfully.",
        )
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return HttpResponse("SUCCESS")
        return super().form_valid(form)

    def form_invalid(self, form):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return render(
                self.request,
                "accounts/partials/section_form_modal.html",
                {
                    "form": form,
                    "action_url": self.request.path,
                },
            )
        return super().form_invalid(form)


class SectionDeleteView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    View,
):
    def get(self, request, pk, *args, **kwargs):
        section = get_object_or_404(Section, pk=pk)
        name = section.name
        section.delete()
        messages.success(
            request,
            f"Section '{name}' deleted successfully.",
        )
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "success", "message": f"Section '{name}' deleted successfully."})
        return redirect("accounts:profile")

    def post(self, request, pk, *args, **kwargs):
        return self.get(request, pk, *args, **kwargs)


class GroupListView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    ListView,
):
    model = Group
    context_object_name = "groups"


class PermissionListView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    ListView,
):
    model = Permission
    context_object_name = "permissions"


class SessionListView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    ListView,
):
    model = Session
    context_object_name = "sessions"


class AuditLogListView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    ListView,
):
    model = AuditLogEntry
    context_object_name = "audit_logs"


class IPRestrictionListView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    ListView,
):
    model = IPRestriction
    context_object_name = "ip_restrictions"


class UserSessionListView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    ListView,
):
    model = UserSession
    context_object_name = "user_sessions"


class PasswordHistoryListView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    ListView,
):
    model = UserPasswordHistory
    context_object_name = "password_history"


class SystemConfigurationView(
    WanjalaMixin,
    SuperUserRequiredMixin,
    TemplateView,
):
    template_name = "accounts/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["configuration"] = (
            SystemConfiguration.current()
        )
        return context