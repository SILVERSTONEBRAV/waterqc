"""Superuser-only hard deletion for CA records and every dependent app row."""

from django.core.exceptions import PermissionDenied

from core.engine.superuser_authorization import force_delete_objects


def delete_ca_objects(objects, *, actor):
    """Delete CA roots and all dependent records for an active superuser."""
    if not getattr(actor, "is_superuser", False) or not getattr(actor, "is_active", False):
        raise PermissionDenied("Only a superuser can force-delete CA records.")

    objects = list(objects)
    if not objects:
        return 0
    if any(obj._meta.app_label != "ca" for obj in objects):
        raise PermissionDenied("Only CA records can be force-deleted here.")
    return force_delete_objects(objects, actor=actor)


def delete_object_for_actor(instance, *, actor):
    """Keep the historical CA helper routed through the shared hard-delete path."""
    if instance._meta.app_label != "ca":
        return instance.delete()
    return delete_ca_objects([instance], actor=actor)
