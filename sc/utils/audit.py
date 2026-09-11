# sc/utils/audit.py
from django.apps import apps
from django.db import connection
from django.contrib.contenttypes.models import ContentType
from ..models import AuditLog
import logging

logger = logging.getLogger(__name__)

SYSTEM_MODELS_TO_SKIP = [
    'migration', 'permission', 'contenttype'
]

# Temporary storage for snapshots per instance
_snapshot_cache = {}


def _store_snapshot(instance):
    """
    Store the current field values of an instance to detect changes later.
    """
    key = (instance.__class__, instance.pk)
    if instance.pk is not None:
        _snapshot_cache[key] = {f.name: getattr(instance, f.name) for f in instance._meta.fields}


def _pop_snapshot(instance):
    """
    Retrieve and remove the stored snapshot for an instance.
    """
    key = (instance.__class__, instance.pk)
    return _snapshot_cache.pop(key, None)


def _log_change(instance, action, user=None, before=None, after=None):
    """
    Safely create an AuditLog record.
    Skips logging during migrations, for system/unmanaged models, or if ContentType table doesn't exist yet.
    """
    try:
        if not apps.ready:
            return

        if 'django_content_type' not in connection.introspection.table_names():
            return

        model_name = instance._meta.model_name.lower()
        if model_name in SYSTEM_MODELS_TO_SKIP or instance._meta.managed is False:
            return

        ct = ContentType.objects.get_for_model(instance.__class__)
        AuditLog.objects.create(
            user=user,
            action=action,
            content_type=ct,
            object_id=str(getattr(instance, "pk", "")),
            object_repr=str(instance)[:512],
            changes={"before": before, "after": after} if before or after else None,
        )

    except Exception:
        logger.debug(f"Skipping AuditLog creation for {instance} during migration or system model.")


# ----------------------------
# Bulk audit for handover takeover
# ----------------------------
def create_bulk_audit(user, instance, assignments, action='bulk_takeover', before=None, after=None):
    """
    Create a single AuditLog for a bulk takeover of multiple ShiftAssignments.

    Args:
        user: The user performing the takeover (typically incoming supervisor)
        instance: The ShiftHandover instance triggering the bulk action
        assignments: Iterable of ShiftAssignment IDs affected
        action: Audit action label
        before: Optional snapshot before change
        after: Optional snapshot after change
    """
    try:
        if not assignments:
            return

        if not apps.ready or 'django_content_type' not in connection.introspection.table_names():
            return

        model_name = instance._meta.model_name.lower()
        if model_name in SYSTEM_MODELS_TO_SKIP or instance._meta.managed is False:
            return

        ct = ContentType.objects.get_for_model(instance.__class__)

        AuditLog.objects.create(
            user=user,
            action=action,
            content_type=ct,
            object_id=str(getattr(instance, "pk", "")),
            object_repr=str(instance)[:512],
            changes={
                "before": before,
                "after": after,
                "assignments": list(assignments)
            },
        )
    except Exception as e:
        logger.debug(f"Failed to create bulk audit for {instance}: {e}")
