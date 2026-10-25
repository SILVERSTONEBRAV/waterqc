"""Shared authorization rules for chemical-analysis domain actions."""

from django.core.exceptions import PermissionDenied


def require_ca_actor(actor, permission=None, *, plant_id=None, active=True):
    """Authorize a CA command consistently across views, admin, and tasks.

    A system action must use an explicit service path rather than passing an
    anonymous or inactive user as an actor. Active superusers bypass CA
    permissions and treatment-plant scope, matching the project policy.
    """
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Sign in to perform this chemical-analysis action.")
    if active and not getattr(actor, "is_active", False):
        raise PermissionDenied("An inactive user cannot perform this chemical-analysis action.")
    if getattr(actor, "is_superuser", False):
        return actor
    if permission and not actor.has_perm(permission):
        raise PermissionDenied("You do not have permission to perform this chemical-analysis action.")
    if plant_id is not None and getattr(actor, "assigned_treatment_plant_id", None) != plant_id:
        raise PermissionDenied("This record is outside your treatment-plant scope.")
    return actor
