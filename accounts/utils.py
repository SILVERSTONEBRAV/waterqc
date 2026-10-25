from typing import Optional, List, Dict, Union
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, QuerySet
from asgiref.sync import sync_to_async
from typing import Dict
from .models import CustomUser
from accounts.serializers import CustomUserSerializer
import logging
from django.conf import settings
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.shortcuts import resolve_url
from django.urls import NoReverseMatch

logger = logging.getLogger(__name__)


def get_user_groups(user):



    try:
        return sorted(
            {
                str(name).strip().upper()
                for name in user.groups.values_list(
                    "name",
                    flat=True,
                )
            }
        )
    except Exception:
        return []


def resolve_redirect_target(target):


    if target is None:
        raise ImproperlyConfigured(
            "Redirect target is None"
        )

    target = str(target).strip()

    if not target:
        raise ImproperlyConfigured(
            "Redirect target is empty"
        )

    try:
        if target.startswith("/"):
            return target

        return resolve_url(target)

    except NoReverseMatch as exc:
        raise ImproperlyConfigured(
            f"Invalid redirect target: {target}"
        ) from exc


def get_user_landing_url(user):


    if user is None:
        raise PermissionDenied(
            "User object missing"
        )

    username = getattr(
        user,
        "username",
        "unknown"
    )

    # -------------------------
    # SUPERUSER
    # -------------------------
    if user.is_superuser:

        target = getattr(
            settings,
            "SUPERUSER_LANDING_MAP",
            "/",
        )

        resolved = resolve_redirect_target(
            target
        )

        logger.debug(
            "LANDING_SUPERUSER user=%s target=%s",
            username,
            resolved,
        )

        return resolved

    # -------------------------
    # GROUP MAPPING
    # DB-managed map takes precedence over settings map.
    # -------------------------
    # 1. Try DB-managed GroupDashboardRedirect table
    db_map = {}
    try:
        from core.models import GroupDashboardRedirect
        db_map = GroupDashboardRedirect.get_redirect_map()
    except Exception:
        pass

    # 2. Settings-level fallback map
    settings_map = getattr(
        settings,
        "LOGIN_GROUP_REDIRECT_MAP",
        {},
    ) or {}

    # Merge: DB entries shadow matching settings entries
    merged_map = {
        str(k).strip().upper(): v
        for k, v in settings_map.items()
        if v
    }
    merged_map.update(db_map)  # DB wins on collision

    groups = get_user_groups(user)

    if not groups:

        fallback = getattr(
            settings,
            "DEFAULT_DASHBOARD_URL",
            "/",
        )

        logger.warning(
            "LANDING_NO_GROUPS user=%s fallback=%s",
            username,
            fallback,
        )

        return resolve_redirect_target(
            fallback
        )

    for group in groups:

        target = merged_map.get(group)

        if not target:
            continue

        try:

            resolved = resolve_redirect_target(
                target
            )

            logger.debug(
                "LANDING_GROUP_MATCH user=%s group=%s target=%s",
                username,
                group,
                resolved,
            )

            return resolved

        except Exception:
            logger.exception(
                "LANDING_GROUP_ERROR user=%s group=%s",
                username,
                group,
            )

    # -------------------------
    # DEFAULT FALLBACK
    # -------------------------
    fallback = getattr(
        settings,
        "DEFAULT_DASHBOARD_URL",
        "/",
    )

    logger.warning(
        "LANDING_FALLBACK user=%s target=%s",
        username,
        fallback,
    )

    return resolve_redirect_target(
        fallback
    )

def lockout_response(request, *args, **kwargs) -> HttpResponse:

    return HttpResponse(
        _('Account locked due to too many failed login attempts. Please try again later.'),
        status=403
    )

def get_user_contact(user_id: int) -> Optional[Dict[str, Union[int, str, bool]]]:

    try:
        user = CustomUser.objects.select_related("section", "assigned_treatment_plant")\
                                 .prefetch_related("groups").get(id=user_id)
        if not user.is_active or user.is_locked:
            return None

        pref = getattr(user, "alert_preferences", None)
        return {
            "id": user.id,
            "email": user.email if (not pref or pref.receive_email) else None,
            "mobile_number": user.mobile_number if (not pref or pref.receive_sms) else None,
            "push_enabled": pref.receive_push if pref else True,
            "section": {"id": user.section.id, "name": user.section.name} if user.section else None,
            "groups": [{"id": g.id, "name": g.name} for g in user.groups.all()],
            "assigned_treatment_plant": {
                "id": user.assigned_treatment_plant.id,
                "name": user.assigned_treatment_plant.name
            } if user.assigned_treatment_plant else None,
        }
    except CustomUser.DoesNotExist:
        return None

def get_active_users_contacts(
        section: Optional[str] = None,
        include_locked: bool = False
) -> List[Dict]:

    qs: QuerySet = CustomUser.objects.select_related("section", "assigned_treatment_plant")\
                                     .prefetch_related("groups")

    if not include_locked:
        qs = qs.filter(is_active=True, is_locked=False)

    if section:
        qs = qs.filter(section__code=section)

    contacts = []
    for u in qs:
        pref = getattr(u, "alert_preferences", None)
        contact = {
            "id": u.id,
            "email": u.email if (not pref or pref.receive_email) else None,
            "mobile_number": u.mobile_number if (not pref or pref.receive_sms) else None,
            "push_enabled": pref.receive_push if pref else True,
            "section": {"id": u.section.id, "name": u.section.name} if u.section else None,
            "groups": [{"id": g.id, "name": g.name} for g in u.groups.all()],
            "assigned_treatment_plant": {
                "id": u.assigned_treatment_plant.id,
                "name": u.assigned_treatment_plant.name
            } if u.assigned_treatment_plant else None,
        }
        if contact["email"] or contact["mobile_number"]:
            contacts.append(contact)

    return contacts

def get_contacts_for_alert(
        user_ids: Optional[List[int]] = None,
        sections: Optional[List[str]] = None,
        groups: Optional[List[int]] = None,
        treatment_plants: Optional[List[int]] = None,
        include_locked: bool = False,
        ai_recommended_user_ids: Optional[List[int]] = None
) -> List[Dict]:

    qs: QuerySet = CustomUser.objects.select_related("section", "assigned_treatment_plant")\
                                     .prefetch_related("groups")

    if not include_locked:
        qs = qs.filter(is_active=True, is_locked=False)

    # Combine filters as OR union of recipients
    filters = Q()
    if user_ids:
        filters |= Q(id__in=user_ids)
    if ai_recommended_user_ids:
        filters |= Q(id__in=ai_recommended_user_ids)
    if sections:
        filters |= Q(section__code__in=sections)
    if groups:
        filters |= Q(groups__id__in=groups)
    if treatment_plants:
        filters |= Q(assigned_treatment_plant__id__in=treatment_plants)

    if filters:
        qs = qs.filter(filters).distinct()

    contacts = []
    for u in qs:
        pref = getattr(u, "alert_preferences", None)
        contacts.append({
            "id": u.id,
            "email": u.email if (not pref or pref.receive_email) else None,
            "mobile_number": u.mobile_number if (not pref or pref.receive_sms) else None,
            "push_enabled": pref.receive_push if pref else True,
            "section": {"id": u.section.id, "name": u.section.name} if u.section else None,
            "groups": [{"id": g.id, "name": g.name} for g in u.groups.all()],
            "assigned_treatment_plant": {
                "id": u.assigned_treatment_plant.id,
                "name": u.assigned_treatment_plant.name
            } if u.assigned_treatment_plant else None,
        })

    return contacts

async def async_get_user_contact(user_id: int) -> Optional[Dict]:
    return await sync_to_async(get_user_contact)(user_id)


async def async_get_active_users_contacts(section: Optional[str] = None, include_locked: bool = False) -> List[Dict]:
    return await sync_to_async(get_active_users_contacts)(section, include_locked)


async def async_get_contacts_for_alert(
        user_ids: Optional[List[int]] = None,
        sections: Optional[List[str]] = None,
        groups: Optional[List[int]] = None,
        treatment_plants: Optional[List[int]] = None,
        include_locked: bool = False,
        ai_recommended_user_ids: Optional[List[int]] = None
) -> List[Dict]:
    return await sync_to_async(get_contacts_for_alert)(
        user_ids, sections, groups, treatment_plants, include_locked, ai_recommended_user_ids
    )




