# ca/mixins.py
from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from core.engine.super_user import SuperUserEngine
from core.mixins import WanjalaMixin

from .navigation import CA_TASK_ACTION_PERMISSIONS, build_ca_sidebar


PLANT_SESSION_KEY = "ca_selected_treatment_plant"
PLANT_QUERY_PARAM = "plant"


class CaWanjalaMixin(WanjalaMixin):
    """
    Chemical Analysis access layer on top of WanjalaMixin.

    - Login / lifecycle / idle timeout come from WanjalaMixin
    - Permission checks use permission_required_view (or legacy `permission`)
    - Plant scope uses assigned plant for staff, selectable plants for superusers
    - Sidebar navigation is built from ca/urls.py via navigation.build_ca_sidebar
    """

    raise_exception = True
    permission_required_view = None
    # Legacy alias still used across ca/views.py; normalized in dispatch.
    permission = None
    plant_query_param = PLANT_QUERY_PARAM
    plant_session_key = PLANT_SESSION_KEY

    def check_permission(self, action=None):
        if self.is_ca_superuser():
            return True
        return super().check_permission(action)

    def has_ca_module_access(self, user=None):
        user = user if user is not None else getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if self.is_ca_superuser(user):
            return True
        all_perms = user.get_all_permissions()
        return any(p.startswith("ca.") for p in all_perms)

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self._normalize_permission_required()

        # This module-level check runs before LoginRequiredMixin.dispatch().
        # Let the standard login redirect handle anonymous users instead of
        # turning a missing session into a 403 response.
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not self.has_ca_module_access(request.user):
            raise PermissionDenied(
                "You do not have permission to access the Chemical Analysis module."
            )

        if not self.is_ca_superuser(request.user):
            self.ensure_user_has_plant()

        if self.permission_required_view and not self.check_permission("view"):
            raise PermissionDenied(
                "You do not have permission to access this Chemical Analysis view."
            )

        self.resolve_selected_plant()

        return super().dispatch(request, *args, **kwargs)

    def _normalize_permission_required(self):
        if self.permission_required_view:
            return

        legacy = getattr(self, "permission", None)
        if legacy:
            self.permission_required_view = legacy

    def is_ca_superuser(self, user=None):
        user = user if user is not None else getattr(self.request, "user", None)
        return SuperUserEngine.is_superuser(user)

    def user_has_ca_permission(self, permission, user=None):
        user = user if user is not None else self.request.user
        if not permission:
            return True
        if self.is_ca_superuser(user):
            return True
        return bool(user.is_authenticated and user.has_perm(permission))

    def ensure_user_has_plant(self):
        if self.is_ca_superuser():
            return None

        plant_id = getattr(self.request.user, "assigned_treatment_plant_id", None)
        if plant_id is None:
            raise PermissionDenied(
                "Your account is not assigned to a treatment plant."
            )
        return plant_id

    def resolve_selected_plant(self):
        """
        Persist superuser plant filter from ?plant= into the session.
        Values: '' / 'all' / missing => all plants; otherwise a plant pk.
        """
        from t.models import TreatmentPlant

        request = self.request
        raw = request.GET.get(self.plant_query_param, None)

        if raw is not None and self.is_ca_superuser():
            if raw in {"", "all", "*"}:
                request.session.pop(self.plant_session_key, None)
            else:
                try:
                    plant_id = int(raw)
                except (TypeError, ValueError):
                    plant_id = None

                if (
                    plant_id
                    and TreatmentPlant.objects.filter(pk=plant_id).exists()
                ):
                    request.session[self.plant_session_key] = plant_id
                else:
                    request.session.pop(self.plant_session_key, None)

        return self.get_selected_plant()

    def get_available_plants(self):
        from t.models import TreatmentPlant
        user = getattr(self.request, "user", None)
        if self.is_ca_superuser():
            return TreatmentPlant.objects.all().order_by("name")
        assigned = getattr(user, "assigned_treatment_plant", None) if user else None
        if assigned:
            return TreatmentPlant.objects.filter(pk=assigned.pk)
        if user and user.is_authenticated:
            return TreatmentPlant.objects.filter(assigned_users=user).order_by("name")
        return TreatmentPlant.objects.none()

    def get_selected_plant(self):
        from t.models import TreatmentPlant

        user = self.request.user

        if self.is_ca_superuser():
            session = getattr(self.request, "session", None)
            plant_id = session.get(self.plant_session_key) if session else None
            if not plant_id:
                return None
            return TreatmentPlant.objects.filter(pk=plant_id).first()

        return getattr(user, "assigned_treatment_plant", None)

    def get_scope_plant_id(self):
        plant = self.get_selected_plant()
        if plant is not None:
            return plant.pk

        if self.is_ca_superuser():
            return None

        return getattr(self.request.user, "assigned_treatment_plant_id", None)

    def scope_queryset(self, queryset, field="treatment_plant_id"):
        plant_id = self.get_scope_plant_id()
        if plant_id is None:
            if self.is_ca_superuser():
                return queryset
            return queryset.none()
        return queryset.filter(**{field: plant_id})

    def scope_specification_queryset(self, queryset):
        plant_id = self.get_scope_plant_id()
        if plant_id is None:
            if self.is_ca_superuser():
                return queryset
            return queryset.none()

        return queryset.filter(
            Q(treatment_plant_id=plant_id) | Q(treatment_plant__isnull=True)
        )

    def get_plant_context(self):
        plant = self.get_selected_plant()
        available = list(self.get_available_plants().values("id", "name"))
        is_superuser = self.is_ca_superuser()

        if is_superuser and plant is None:
            plant_name = "All Treatment Plants"
            plant_id = None
        elif plant is not None:
            plant_name = plant.name
            plant_id = plant.pk
        else:
            plant_name = "Current Scope"
            plant_id = None

        return {
            "is_superuser": is_superuser,
            "plant": plant,
            "plant_id": plant_id,
            "plant_name": plant_name,
            "name": plant_name,
            "available_plants": available,
            "allow_all_plants": is_superuser,
            "query_param": self.plant_query_param,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        plant_context = self.get_plant_context() or {}
        context.update(
            {
                "treatment_plant": plant_context.get("plant"),
                "plant_context": plant_context,
                "available_plants": plant_context.get("available_plants", []),
                "selected_plant_id": plant_context.get("plant_id"),
                "ca_sidebar_sections": build_ca_sidebar(self.request),
                "can_view_my_tasks": self.is_ca_superuser()
                or self.request.user.has_perm("ca.view_chemicalanalysisprocess")
                or any(
                    self.request.user.has_perm(permission)
                    for permission in CA_TASK_ACTION_PERMISSIONS
                ),
            }
        )
        if "dashboard" in getattr(self, "template_name", ""):
            from .models import (
                Chemical,
                ChemicalBatch,
                ChemicalLocation,
                Supplier,
            )

            may_view_batches = self.is_ca_superuser() or self.request.user.has_perm(
                "ca.view_chemicalbatch"
            )
            if may_view_batches:
                batches = self.scope_queryset(
                    ChemicalBatch.objects.all(),
                    field="treatment_plant_id",
                )
                chemical_ids = batches.values_list(
                    "chemical_id", flat=True
                ).distinct()
                supplier_ids = batches.values_list(
                    "supplier_id", flat=True
                ).distinct()
                context.setdefault(
                    "chemicals",
                    list(
                        Chemical.objects.filter(pk__in=chemical_ids).order_by(
                            "name"
                        )
                    ),
                )
                context.setdefault(
                    "suppliers",
                    list(
                        Supplier.objects.filter(pk__in=supplier_ids).order_by(
                            "name"
                        )
                    ),
                )
                locations = ChemicalLocation.objects.select_related(
                    "treatment_plant"
                ).order_by("treatment_plant__name", "name")
                plant_id = plant_context.get("plant_id")
                if plant_id is not None:
                    locations = locations.filter(treatment_plant_id=plant_id)
                elif not plant_context.get("is_superuser"):
                    locations = locations.none()
                context["chemical_locations"] = list(locations)
            else:
                context.setdefault("chemicals", [])
                context.setdefault("suppliers", [])
                context["chemical_locations"] = []
        return context
