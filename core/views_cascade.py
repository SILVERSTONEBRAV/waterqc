# core/views_cascade.py
from __future__ import annotations

import logging
from typing import Any, Dict, List
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core.models import Section
from t.models import TreatmentPlant

logger = logging.getLogger(__name__)
User = get_user_model()


@login_required
@require_GET
def plant_sections_api(request) -> JsonResponse:
    """
    Returns active sections filtered by treatment plant.
    When a treatment plant is selected, only sections belonging to that plant
    (or global sections if unassigned) are listed.
    """
    plant_param = (
        request.GET.get("treatment_plant")
        or request.GET.get("treatment_plant_id")
        or request.GET.get("plant")
        or request.GET.get("plant_id")
    )

    qs = Section.objects.filter(is_active=True).select_related("treatment_plant")

    if plant_param:
        if str(plant_param).isdigit():
            # Include sections assigned to this plant, plus any unassigned/global sections
            qs = qs.filter(
                Q(treatment_plant_id=int(plant_param)) | Q(treatment_plant__isnull=True)
            )
        else:
            qs = qs.filter(
                Q(treatment_plant__name__iexact=str(plant_param).strip())
                | Q(treatment_plant__code__iexact=str(plant_param).strip())
                | Q(treatment_plant__isnull=True)
            )

    sections_data = [
        {
            "id": s.id,
            "code": s.code,
            "name": s.name,
            "label": f"{s.name} ({s.code})" if s.code else s.name,
            "treatment_plant_id": s.treatment_plant_id,
            "treatment_plant_name": s.treatment_plant.name if s.treatment_plant else "",
        }
        for s in qs.order_by("name")
    ]

    return JsonResponse({
        "success": True,
        "count": len(sections_data),
        "sections": sections_data,
    })


@login_required
@require_GET
def section_users_api(request) -> JsonResponse:
    """
    Returns active users filtered by section and optionally treatment plant.
    After a section is selected, lists only users belonging to that section.
    """
    section_param = (
        request.GET.get("section")
        or request.GET.get("section_id")
    )
    plant_param = (
        request.GET.get("treatment_plant")
        or request.GET.get("treatment_plant_id")
        or request.GET.get("plant")
        or request.GET.get("plant_id")
    )

    qs = User.objects.filter(is_active=True).select_related("section", "assigned_treatment_plant")

    if section_param:
        if str(section_param).isdigit():
            qs = qs.filter(section_id=int(section_param))
        else:
            qs = qs.filter(
                Q(section__code__iexact=str(section_param).strip())
                | Q(section__name__iexact=str(section_param).strip())
            )

    if plant_param:
        if str(plant_param).isdigit():
            plant_id = int(plant_param)
            qs = qs.filter(
                Q(assigned_treatment_plant_id=plant_id)
                | Q(section__treatment_plant_id=plant_id)
            )
        else:
            plant_str = str(plant_param).strip()
            qs = qs.filter(
                Q(assigned_treatment_plant__name__iexact=plant_str)
                | Q(assigned_treatment_plant__code__iexact=plant_str)
                | Q(section__treatment_plant__name__iexact=plant_str)
            )

    users_data = [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.get_full_name() or u.username,
            "name": u.get_full_name() or u.username,
            "label": f"{u.get_full_name()} ({u.username})" if u.get_full_name() else u.username,
            "email": u.email,
            "section_id": u.section_id,
            "section_name": u.section.name if u.section else "",
            "treatment_plant_id": u.assigned_treatment_plant_id,
            "treatment_plant_name": u.assigned_treatment_plant.name if u.assigned_treatment_plant else "",
        }
        for u in qs.order_by("username")
    ]

    return JsonResponse({
        "success": True,
        "count": len(users_data),
        "users": users_data,
    })


@login_required
@require_GET
def cascade_hierarchy_api(request) -> JsonResponse:
    """
    Returns full hierarchy metadata (plants, sections grouped by plant, and users grouped by section)
    for instant client-side dropdown resolution without latency.
    """
    plants = [
        {"id": p.id, "name": p.name, "code": p.code}
        for p in TreatmentPlant.objects.all().order_by("name")
    ]

    sections = [
        {
            "id": s.id,
            "name": s.name,
            "code": s.code,
            "treatment_plant_id": s.treatment_plant_id,
        }
        for s in Section.objects.filter(is_active=True).order_by("name")
    ]

    users = [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.get_full_name() or u.username,
            "section_id": u.section_id,
            "treatment_plant_id": u.assigned_treatment_plant_id,
        }
        for u in User.objects.filter(is_active=True).only("id", "username", "first_name", "last_name", "section_id", "assigned_treatment_plant_id").order_by("username")
    ]

    return JsonResponse({
        "success": True,
        "plants": plants,
        "sections": sections,
        "users": users,
    })
