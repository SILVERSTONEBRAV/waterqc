from django.urls import path

from .authViews import (
    CheckUsernameView,
    ResetPasswordRequestView,
    ChangePasswordView,
)

from .LoginView import LoginView
from .LogoutView import LogoutView

from .ProfileView import (
    ProfileView,
    ProfilePictureUpdateView,
    UserListView,
    UserCreateView,
    UserUpdateView,
    UserDeleteView,
    SectionListView,
    GroupListView,
    PermissionListView,
    SessionListView,
    UserSessionListView,
    PasswordHistoryListView,
    AuditLogListView,
    IPRestrictionListView,
    SystemConfigurationView,
)

app_name = "accounts"

urlpatterns = [

    # =========================
    # AUTH / SESSION
    # =========================
    path("", ProfileView.as_view(), name="dashboard"),
    path("profile/", ProfileView.as_view(), name="profile"),

    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("check-username/", CheckUsernameView.as_view(), name="check_username"),
    path("reset-password-request/", ResetPasswordRequestView.as_view(), name="reset_password_request"),

    # =========================
    # PROFILE
    # =========================
    path(
        "profile/picture/",
        ProfilePictureUpdateView.as_view(),
        name="profile_picture_update",
    ),

    # =========================
    # USER MANAGEMENT
    # =========================
    path("admin/users/", UserListView.as_view(), name="user_list"),
    path("admin/users/create/", UserCreateView.as_view(), name="user_create"),
    path("admin/users/<int:pk>/edit/", UserUpdateView.as_view(), name="user_update"),
    path("admin/users/<int:pk>/delete/", UserDeleteView.as_view(), name="user_delete"),

    path("admin/sections/", SectionListView.as_view(), name="section_list"),
    path("admin/groups/", GroupListView.as_view(), name="group_list"),
    path("admin/permissions/", PermissionListView.as_view(), name="permission_list"),

    # =========================
    # SYSTEM MONITORING
    # =========================
    path("admin/sessions/", SessionListView.as_view(), name="session_list"),
    path("admin/user-sessions/", UserSessionListView.as_view(), name="user_session_list"),
    path("admin/password-history/", PasswordHistoryListView.as_view(), name="password_history_list"),
    path("admin/audit-logs/", AuditLogListView.as_view(), name="audit_log_list"),
    path("admin/ip-restrictions/", IPRestrictionListView.as_view(), name="ip_restriction_list"),
    path("admin/configuration/", SystemConfigurationView.as_view(), name="configuration"),
]