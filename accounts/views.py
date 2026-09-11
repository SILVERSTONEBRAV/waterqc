# accounts/views.py

from django.views.generic import TemplateView
from django.shortcuts import (
    get_object_or_404,
    redirect,
)
from django.http import (
    JsonResponse,
    HttpResponse,
)
from django.forms import modelform_factory

from core.mixins import WanjalaMixin
from .models import CustomUser


class UserBaseView(
    WanjalaMixin,
    TemplateView,
):
    model = CustomUser

    template_name = "accounts/users/list.html"

    row_template_name = (
        "accounts/users/partials/row.html"
    )

    list_template_name = (
        "accounts/users/partials/list.html"
    )

    default_paginate_by = 50

    export_file_name = "users"

    inline_edit_fields = [
        "first_name",
        "last_name",
        "email",
        "mobile_number",
        "section",
        "assigned_lab",
        "assigned_treatment_plant",
        "is_active",
        "is_locked",
        "email_verified",
        "mfa_enabled",
        "groups",
        "user_permissions",
    ]

    form_class = modelform_factory(
        CustomUser,
        exclude=[],
    )

    action = "view"

    def get_object(self):
        pk = (
            self.kwargs.get("pk")
            or self.request.GET.get("pk")
            or self.request.POST.get("pk")
        )

        if not pk:
            return None

        return get_object_or_404(
            self.model,
            pk=pk,
        )

    def get_context_data(
        self,
        **kwargs,
    ):
        ctx = super().get_context_data(
            **kwargs
        )

        qs = self.get_queryset()

        paginator, page_obj, objects, is_paginated = (
            self.paginate_queryset(qs)
        )

        ctx.update(
            {
                "objects": objects,
                "page_obj": page_obj,
                "paginator": paginator,
                "is_paginated": is_paginated,
                "stats": self.get_stats(),
                "ui_permissions": self.get_ui_permissions(),
                "runtime": self.build_user_runtime_context(
                    self.request
                ),
            }
        )

        return ctx

    def get_stats(self):
        qs = self.get_queryset()

        return {
            "total": qs.count(),
            "active": qs.filter(
                is_active=True
            ).count(),
            "inactive": qs.filter(
                is_active=False
            ).count(),
            "locked": qs.filter(
                is_locked=True
            ).count(),
            "mfa": qs.filter(
                mfa_enabled=True
            ).count(),
            "staff": qs.filter(
                is_staff=True
            ).count(),
            "superusers": qs.filter(
                is_superuser=True
            ).count(),
        }