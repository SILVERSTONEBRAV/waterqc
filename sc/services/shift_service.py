# sc/services/shift_service.py
from __future__ import annotations

import logging
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any, List

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction

from t.models import TreatmentPlant
from sc.models import (
    Shift,
    ShiftHandover,
    ShiftAssignment,
    ShiftSupervisor,
    Apparatus,
    ApparatusCondition
)

logger = logging.getLogger(__name__)
User = get_user_model()


def ensure_default_shifts(plant: TreatmentPlant) -> List[Shift]:
    """
    Ensure standard utility shifts exist for the given treatment plant:
      1. Morning Shift:   06:00 - 14:00 (Handover: 13:45, Takeover: 14:00)
      2. Afternoon Shift: 14:00 - 22:00 (Handover: 21:45, Takeover: 22:00)
      3. Night Shift:     22:00 - 06:00 (Handover: 05:45, Takeover: 06:00)
    """
    existing = list(Shift.objects.filter(treatment_plant=plant, is_deleted=False))
    if existing:
        return existing

    defaults = [
        {
            "name": "Morning Shift",
            "start_time": time(6, 0),
            "end_time": time(14, 0),
            "handover_time": time(13, 45),
            "takeover_time": time(14, 0),
        },
        {
            "name": "Afternoon Shift",
            "start_time": time(14, 0),
            "end_time": time(22, 0),
            "handover_time": time(21, 45),
            "takeover_time": time(22, 0),
        },
        {
            "name": "Night Shift",
            "start_time": time(22, 0),
            "end_time": time(6, 0),
            "handover_time": time(5, 45),
            "takeover_time": time(6, 0),
        },
    ]

    created_shifts = []
    for data in defaults:
        shift, _ = Shift.objects.get_or_create(
            treatment_plant=plant,
            name=data["name"],
            defaults={
                "start_time": data["start_time"],
                "end_time": data["end_time"],
                "handover_time": data["handover_time"],
                "takeover_time": data["takeover_time"],
                "is_deleted": False,
            }
        )
        created_shifts.append(shift)

    logger.info("Created default shifts for plant %s", plant.name)
    return created_shifts


def get_next_shift(current_shift: Shift, plant: TreatmentPlant) -> Optional[Shift]:
    """
    Finds the next shift following the current shift in rotation.
    """
    shifts = list(
        Shift.objects.filter(treatment_plant=plant, is_deleted=False).order_by("start_time")
    )
    if not shifts:
        return None

    try:
        idx = shifts.index(current_shift)
        return shifts[(idx + 1) % len(shifts)]
    except ValueError:
        # Fallback by start_time
        for s in shifts:
            if s.start_time >= current_shift.end_time:
                return s
        return shifts[0]


def check_handover_window(shift: Shift, now: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Determines if current time is within ±15 minutes of shift handover time.
    """
    now = now or timezone.localtime()
    current_date = now.date()

    expected_handover_time = shift.handover_time or shift.end_time
    expected_takeover_time = shift.takeover_time or shift.end_time

    # Construct expected datetime
    expected_dt = datetime.combine(current_date, expected_handover_time)
    if shift.is_overnight and expected_handover_time < shift.start_time:
        # Expected handover is on next day
        expected_dt += timedelta(days=1)

    expected_dt = timezone.make_aware(expected_dt, timezone.get_current_timezone())

    window_start = expected_dt - timedelta(minutes=15)
    window_end = expected_dt + timedelta(minutes=15)

    is_active = window_start <= now <= window_end

    return {
        "is_active": is_active,
        "window_start": window_start,
        "window_end": window_end,
        "window_display": f"{window_start.strftime('%H:%M')} – {window_end.strftime('%H:%M')}",
        "expected_handover_time": expected_handover_time.strftime("%H:%M"),
        "expected_takeover_time": expected_takeover_time.strftime("%H:%M"),
    }


def get_current_shift_data(user, request=None) -> Dict[str, Any]:
    """
    Returns complete shift telemetry and supervisor info for the active user session.
    """
    # 1. Resolve Treatment Plant
    plant = getattr(user, "assigned_treatment_plant", None)
    if not plant:
        plant = TreatmentPlant.objects.filter(code="NGH").first() or TreatmentPlant.objects.first()

    if not plant:
        return {
            "plant": None,
            "current_shift": None,
            "next_shift": None,
            "supervisor": None,
            "is_handover_window_active": False,
            "handover_window_time": "",
        }

    # 2. Ensure shifts exist
    shifts = ensure_default_shifts(plant)

    # 3. Get current shift
    now = timezone.localtime()
    current_shift = Shift.get_shift_for_time(now, treatment_plant=plant)
    if not current_shift and shifts:
        current_shift = shifts[0]

    # 4. Get next shift in rotation
    next_shift = get_next_shift(current_shift, plant) if current_shift else None

    # 5. Resolve active Shift Supervisor
    supervisor = None
    if current_shift:
        # Check if handover already occurred today
        latest_handover = (
            ShiftHandover.objects
            .filter(shift=current_shift, date=now.date())
            .order_by("-handed_over_at")
            .first()
        )
        if latest_handover and latest_handover.is_taken_over and latest_handover.incoming_supervisor:
            supervisor = latest_handover.incoming_supervisor
        elif latest_handover and latest_handover.outgoing_supervisor:
            supervisor = latest_handover.outgoing_supervisor

        if not supervisor:
            # Check shift assignment for today
            assignment = (
                ShiftAssignment.objects
                .filter(shift=current_shift, date=now.date(), is_deleted=False)
                .exclude(supervisor=None)
                .first()
            )
            if assignment:
                supervisor = assignment.effective_supervisor

        if not supervisor:
            # Check designated plant ShiftSupervisor (prefer matching user section)
            user_section = getattr(user, "section", None)
            shift_sup = None
            if user_section:
                shift_sup = ShiftSupervisor.objects.filter(
                    treatment_plant=plant, section=user_section, is_active=True
                ).first()
            if not shift_sup:
                shift_sup = ShiftSupervisor.objects.filter(treatment_plant=plant, is_active=True).first()
            if shift_sup:
                supervisor = shift_sup.user

        if not supervisor:
            # Fallback to active staff user if staff/superuser
            if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
                supervisor = user

    # 6. Handover window check
    window_data = check_handover_window(current_shift, now) if current_shift else {"is_active": False, "window_display": ""}

    is_window_active = window_data["is_active"]
    # Allow superusers / staff to initiate handover for testing/admin purposes
    if getattr(user, "is_superuser", False):
        is_window_active = True

    return {
        "plant": plant,
        "current_shift": current_shift,
        "next_shift": next_shift,
        "supervisor": supervisor,
        "is_handover_window_active": is_window_active,
        "handover_window_time": window_data.get("window_display", ""),
        "window_data": window_data,
    }


def user_belongs_to_shift(user, shift: Shift, target_date: Optional[date] = None) -> bool:
    """
    Checks if a user belongs to the specified shift.
    Superusers automatically have cross-shift authorization.
    """
    if getattr(user, "is_superuser", False):
        return True

    target_date = target_date or timezone.localdate()

    # 1. Direct ShiftAssignment
    has_assignment = ShiftAssignment.objects.filter(
        staff=user,
        shift=shift,
        date=target_date,
        is_deleted=False
    ).exists()
    if has_assignment:
        return True

    # 2. Supervised assignments
    is_supervisor_of_shift = ShiftAssignment.objects.filter(
        supervisor=user,
        shift=shift,
        date=target_date,
        is_deleted=False
    ).exists()
    if is_supervisor_of_shift:
        return True

    # 3. Designated ShiftSupervisor for the plant
    is_plant_supervisor = ShiftSupervisor.objects.filter(
        user=user,
        treatment_plant=shift.treatment_plant,
        is_active=True
    ).exists()
    if is_plant_supervisor:
        return True

    # 4. If system has no ShiftAssignment records in DB for target_date yet:
    # Any active user assigned to this treatment plant is considered eligible
    total_assignments_for_date = ShiftAssignment.objects.filter(
        shift__treatment_plant=shift.treatment_plant,
        date=target_date,
        is_deleted=False
    ).count()

    if total_assignments_for_date == 0:
        if getattr(user, "assigned_treatment_plant_id", None) == shift.treatment_plant_id:
            return True
        if user.is_staff:
            return True

    return False


def get_eligible_supervisors_for_shift(shift: Shift, target_date: Optional[date] = None) -> List[User]:
    """
    Returns users who belong to the target shift and can take over or hand over.
    """
    target_date = target_date or timezone.localdate()
    eligible = set()

    # 1. Staff assigned to this shift today
    assigned_staff_ids = ShiftAssignment.objects.filter(
        shift=shift,
        date=target_date,
        is_deleted=False
    ).values_list("staff_id", flat=True)
    for u in User.objects.filter(id__in=assigned_staff_ids, is_active=True):
        eligible.add(u)

    # 2. Supervisors assigned to this shift today
    supervisor_ids = ShiftAssignment.objects.filter(
        shift=shift,
        date=target_date,
        is_deleted=False
    ).exclude(supervisor=None).values_list("supervisor_id", flat=True)
    for u in User.objects.filter(id__in=supervisor_ids, is_active=True):
        eligible.add(u)

    # 3. Designated plant shift supervisors
    plant_supervisors = ShiftSupervisor.objects.filter(
        treatment_plant=shift.treatment_plant,
        is_active=True
    ).select_related("user")
    for ps in plant_supervisors:
        eligible.add(ps.user)

    # 4. Fallback if roster is empty: all active staff assigned to this plant + superusers
    if not eligible:
        plant_users = User.objects.filter(
            assigned_treatment_plant=shift.treatment_plant,
            is_active=True
        )
        for u in plant_users:
            eligible.add(u)

    # Always include superusers as overseers
    superusers = User.objects.filter(is_superuser=True, is_active=True)
    for su in superusers:
        eligible.add(su)

    return sorted(list(eligible), key=lambda u: (not u.is_superuser, u.get_full_name() or u.username))


def seed_default_apparatus_if_needed(plant: TreatmentPlant) -> List[Apparatus]:
    """
    Ensures baseline equipment and apparatus exist for the handover checklist.
    """
    from core.models import Section
    from inventory.models import Category, Equipment

    existing = list(Apparatus.objects.all())
    if existing:
        return existing

    section = Section.objects.first()
    if not section:
        section = Section.objects.create(name="Quality Assurance & Operations")

    category, _ = Category.objects.get_or_create(
        name="Laboratory & Operations Apparatus",
        defaults={"description": "Critical plant analytical equipment and instrumentation"}
    )

    items = [
        {"name": "Laboratory Turbidimeter", "desc": "Benchtop turbidimeter for settled & treated water compliance"},
        {"name": "Digital pH / Temperature Meter", "desc": "Calibrated dual-electrode pH/Temp sensor for raw & coagulated water"},
        {"name": "Chlorine Residual Photometer", "desc": "DPD colorimetric online/benchtop free and total chlorine analyzer"},
        {"name": "Jar Test Flocculator Unit", "desc": "6-paddle automated jar tester for coagulant dose optimization"},
        {"name": "Online Filter Turbidity Monitor", "desc": "Continuous Nephelometric monitor for rapid sand filter bank"},
    ]

    created = []
    for i, it in enumerate(items, 1):
        eq, _ = Equipment.objects.get_or_create(
            serial_number=f"APP-{plant.code or 'NGH'}-{i:03d}",
            defaults={
                "name": it["name"],
                "category": category,
                "section": section,
                "next_calibration_date": timezone.localdate() + timedelta(days=90),
                "next_maintenance_date": timezone.localdate() + timedelta(days=60),
            }
        )
        app, _ = Apparatus.objects.get_or_create(
            name=it["name"],
            defaults={
                "equipment": eq,
                "description": it["desc"]
            }
        )
        created.append(app)

    logger.info("Seeded %d apparatus units for handover tracking.", len(created))
    return created
