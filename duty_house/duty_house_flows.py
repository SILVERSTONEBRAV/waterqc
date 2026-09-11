# duty_house/flows.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from accounts.models import CustomUser

from .models import (
    DutyHouse,
    DutyHouseUnit,
    DutyHouseAllocation,
    DutyHouseOccupancy,
    AllocationStatus,
    OccupancyStatus,
)


# =========================================================
# FLOW RESULT
# =========================================================

@dataclass(slots=True)
class FlowResult:
    success: bool
    message: str
    allocation: Optional[DutyHouseAllocation] = None
    occupancy: Optional[DutyHouseOccupancy] = None


# =========================================================
# VALIDATION ENGINE
# =========================================================

class HousingValidation:

    @staticmethod
    def ensure_unit_active(unit: DutyHouseUnit):
        if not unit.is_active:
            raise ValidationError("Unit is inactive.")

    @staticmethod
    def ensure_house_active(unit: DutyHouseUnit):
        if not unit.duty_house.is_active:
            raise ValidationError("Duty house is inactive.")

    @staticmethod
    def ensure_house_not_decommissioned(unit: DutyHouseUnit):
        if unit.duty_house.status == "decommissioned":
            raise ValidationError(
                "Duty house has been decommissioned."
            )

    @staticmethod
    def ensure_unit_vacant(unit: DutyHouseUnit):
        if DutyHouseOccupancy.objects.filter(
            unit=unit,
            is_current=True
        ).exists():
            raise ValidationError(
                "Unit is currently occupied."
            )

    @staticmethod
    def ensure_user_not_housed(user: CustomUser):
        if DutyHouseOccupancy.objects.filter(
            user=user,
            is_current=True
        ).exists():
            raise ValidationError(
                "User already occupies a housing unit."
            )

    @classmethod
    def validate_allocation(
        cls,
        unit: DutyHouseUnit,
        user: CustomUser,
    ):
        cls.ensure_unit_active(unit)
        cls.ensure_house_active(unit)
        cls.ensure_house_not_decommissioned(unit)
        cls.ensure_unit_vacant(unit)
        cls.ensure_user_not_housed(user)


# =========================================================
# ALLOCATION FLOW
# =========================================================

class AllocationFlow:

    @staticmethod
    @transaction.atomic
    def allocate(
        *,
        allocation: DutyHouseAllocation,
        user: CustomUser,
        approved_by: Optional[CustomUser] = None,
    ) -> FlowResult:

        allocation = (
            DutyHouseAllocation.objects
            .select_for_update()
            .select_related(
                "unit",
                "unit__duty_house"
            )
            .get(pk=allocation.pk)
        )

        unit = allocation.unit

        HousingValidation.validate_allocation(
            unit=unit,
            user=user,
        )

        allocation.user = user
        allocation.status = AllocationStatus.ALLOCATED
        allocation.allocated_at = timezone.now()

        if allocation.approved_at is None:
            allocation.approved_at = timezone.now()

        allocation.save()

        occupancy = DutyHouseOccupancy.objects.create(
            duty_house=unit.duty_house,
            unit=unit,
            user=user,
            status=OccupancyStatus.ACTIVE,
            is_current=True,
        )

        return FlowResult(
            success=True,
            message="Unit allocated successfully.",
            allocation=allocation,
            occupancy=occupancy,
        )

    @staticmethod
    @transaction.atomic
    def release(
        *,
        allocation: DutyHouseAllocation,
        reason: Optional[str] = None,
    ) -> FlowResult:

        allocation = (
            DutyHouseAllocation.objects
            .select_for_update()
            .select_related("unit")
            .get(pk=allocation.pk)
        )

        occupancy = (
            DutyHouseOccupancy.objects
            .select_for_update()
            .filter(
                unit=allocation.unit,
                is_current=True,
            )
            .first()
        )

        if occupancy:

            occupancy.status = OccupancyStatus.ENDED
            occupancy.is_current = False
            occupancy.end_date = timezone.now()
            occupancy.exit_reason = reason
            occupancy.save()

        allocation.status = AllocationStatus.RELEASED
        allocation.released_at = timezone.now()
        allocation.save()

        return FlowResult(
            success=True,
            message="Allocation released successfully.",
            allocation=allocation,
            occupancy=occupancy,
        )


# =========================================================
# APPROVAL FLOW
# =========================================================

class ApprovalFlow:

    @staticmethod
    @transaction.atomic
    def approve(
        allocation: DutyHouseAllocation,
    ):

        allocation = (
            DutyHouseAllocation.objects
            .select_for_update()
            .get(pk=allocation.pk)
        )

        if allocation.status != AllocationStatus.REQUESTED:
            raise ValidationError(
                "Only requested allocations may be approved."
            )

        allocation.status = AllocationStatus.APPROVED
        allocation.approved_at = timezone.now()
        allocation.save()

        return allocation

    @staticmethod
    @transaction.atomic
    def reject(
        allocation: DutyHouseAllocation,
        reason: str = "",
    ):

        allocation = (
            DutyHouseAllocation.objects
            .select_for_update()
            .get(pk=allocation.pk)
        )

        allocation.status = AllocationStatus.REJECTED
        allocation.save()

        return allocation


# =========================================================
# TRANSFER FLOW
# =========================================================

class TransferFlow:

    @staticmethod
    @transaction.atomic
    def transfer(
        *,
        user: CustomUser,
        destination_unit: DutyHouseUnit,
    ) -> FlowResult:

        current = (
            DutyHouseOccupancy.objects
            .select_for_update()
            .select_related("unit")
            .filter(
                user=user,
                is_current=True
            )
            .first()
        )

        if not current:
            raise ValidationError(
                "User has no active occupancy."
            )

        HousingValidation.ensure_unit_vacant(
            destination_unit
        )

        HousingValidation.ensure_unit_active(
            destination_unit
        )

        current.status = OccupancyStatus.ENDED
        current.is_current = False
        current.end_date = timezone.now()
        current.exit_reason = "Transferred"
        current.save()

        new_occupancy = DutyHouseOccupancy.objects.create(
            duty_house=destination_unit.duty_house,
            unit=destination_unit,
            user=user,
            status=OccupancyStatus.ACTIVE,
            is_current=True,
        )

        return FlowResult(
            success=True,
            message="Occupancy transferred successfully.",
            occupancy=new_occupancy,
        )


# =========================================================
# MAINTENANCE FLOW
# =========================================================

class MaintenanceFlow:

    @staticmethod
    @transaction.atomic
    def open_critical_issue(
        house: DutyHouse,
        impact: float = 5.0,
    ):

        house = (
            DutyHouse.objects
            .select_for_update()
            .get(pk=house.pk)
        )

        house.critical_issues_open += 1

        house.maintenance_score = max(
            0,
            house.maintenance_score - impact
        )

        if house.maintenance_score < 70:
            house.status = "maintenance"

        house.save()

        return house

    @staticmethod
    @transaction.atomic
    def close_critical_issue(
        house: DutyHouse,
        recovery: float = 2.0,
    ):

        house = (
            DutyHouse.objects
            .select_for_update()
            .get(pk=house.pk)
        )

        house.critical_issues_open = max(
            0,
            house.critical_issues_open - 1
        )

        house.maintenance_score = min(
            100,
            house.maintenance_score + recovery
        )

        if (
            house.critical_issues_open == 0
            and house.status == "maintenance"
        ):
            house.status = "active"

        house.save()

        return house


# =========================================================
# OCCUPANCY QUERY SERVICE
# =========================================================

class HousingService:

    @staticmethod
    def current_occupancy(user: CustomUser):

        return (
            DutyHouseOccupancy.objects
            .select_related(
                "unit",
                "duty_house",
            )
            .filter(
                user=user,
                is_current=True,
            )
            .first()
        )

    @staticmethod
    def vacant_units():

        occupied = (
            DutyHouseOccupancy.objects
            .filter(is_current=True)
            .values_list(
                "unit_id",
                flat=True
            )
        )

        return (
            DutyHouseUnit.objects
            .filter(is_active=True)
            .exclude(id__in=occupied)
            .select_related(
                "duty_house"
            )
        )