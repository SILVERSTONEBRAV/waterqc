"""Broadcast committed Django model writes as minimal live refresh hints."""

from __future__ import annotations

import logging
from functools import lru_cache

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.apps import apps
from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.utils import timezone

logger = logging.getLogger(__name__)

_SKIP_APPS = {"admin", "auth", "contenttypes", "sessions", "alerts"}
_SKIP_MODELS = {"qc.qcrealtimeoutboxevent"}


def _plant_id(instance, seen=None):
    """Resolve a plant from direct fields or already-cached related objects."""
    seen = seen or set()
    marker = (instance.__class__, getattr(instance, "pk", None), id(instance))
    if marker in seen:
        return None
    seen.add(marker)
    if instance._meta.model_name in {"treatmentplant", "plant"}:
        return getattr(instance, "pk", None)
    for name in ("treatment_plant_id", "plant_id"):
        value = getattr(instance, name, None)
        if value:
            return value

    for name in ("geo_context", "context", "metadata"):
        value = getattr(instance, name, None)
        if isinstance(value, dict):
            plant_id = value.get("plant_id") or value.get("treatment_plant_id")
            if plant_id:
                return plant_id

    meta = getattr(instance, "_meta", None)
    if not meta:
        return None
    for field in meta.concrete_fields:
        if not getattr(field, "is_relation", False) or not getattr(field, "many_to_one", False):
            continue
        related_model = getattr(field, "related_model", None)
        if related_model and related_model._meta.model_name in {"treatmentplant", "plant"}:
            value = getattr(instance, field.attname, None)
            if value:
                return value

    for related in getattr(getattr(instance, "_state", None), "fields_cache", {}).values():
        if related is not None and related is not instance:
            value = _plant_id(related, seen)
            if value:
                return value

    content_type_id = getattr(instance, "content_type_id", None)
    object_id = getattr(instance, "object_id", None)
    if content_type_id and object_id:
        try:
            content_type = getattr(instance, "content_type", None)
            related_model = content_type.model_class() if content_type else None
            related = related_model._base_manager.filter(pk=object_id).first() if related_model else None
            if related is not None:
                value = _plant_id(related, seen)
                if value:
                    return value
        except Exception:
            pass

    # Resolve uncached relations (for example WorkflowAlert -> Batch -> Plant)
    # with one bounded query. Most models use the direct-field fast path above.
    if getattr(instance, "pk", None):
        manager = instance.__class__._base_manager
        db = getattr(getattr(instance, "_state", None), "db", None)
        if db:
            manager = manager.using(db)
        paths = _plant_paths(instance.__class__)
        if paths:
            try:
                row = manager.filter(pk=instance.pk).values(
                    *[f"{path}__pk" for path in paths]
                ).first() or {}
                for path in paths:
                    value = row.get(f"{path}__pk")
                    if value:
                        return value
            except Exception:
                logger.debug("Could not resolve plant scope for %s", instance._meta.label, exc_info=True)
    return None


@lru_cache(maxsize=None)
def _plant_paths(model):
    """Return short forward-FK paths from a model to a treatment plant."""
    def walk(current, prefix=(), seen=frozenset(), depth=0):
        if current._meta.model_name in {"treatmentplant", "plant"}:
            return [prefix]
        if depth >= 4 or current in seen:
            return []
        paths = []
        next_seen = seen | {current}
        for field in current._meta.concrete_fields:
            related = getattr(field, "related_model", None)
            if not related or not getattr(field, "many_to_one", False) and not getattr(field, "one_to_one", False):
                continue
            paths.extend(walk(related, prefix + (field.name,), next_seen, depth + 1))
        return paths

    return tuple("__".join(path) for path in walk(model) if path)


def _publish(app_label, model_name, action, plant_id):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    # Always notify the app channel as well as the plant channel. This lets
    # authorized all-plant dashboards receive data-free invalidations; the
    # consumer filters plant-specific events before forwarding them.
    groups = [f"live-app-{app_label}"]
    if plant_id:
        groups.append(f"live-plant-{plant_id}")
    event = {
        "type": "data_changed",
        "app_label": app_label,
        "model": model_name,
        "action": action,
        "plant_id": str(plant_id) if plant_id else None,
        "timestamp": timezone.now().isoformat(),
    }
    try:
        for group in groups:
            async_to_sync(channel_layer.group_send)(group, event)
    except Exception:
        logger.exception("Live update broadcast failed for %s.%s", app_label, model_name)


def _saved(sender, instance, created=False, **kwargs):
    if (
        sender._meta.app_label in _SKIP_APPS
        or sender._meta.label_lower in _SKIP_MODELS
        or not instance.pk
    ):
        return
    plant_id = _plant_id(instance)
    transaction.on_commit(
        lambda: _publish(
            sender._meta.app_label,
            sender._meta.model_name,
            "created" if created else "updated",
            plant_id,
        )
    )


def _before_delete(sender, instance, **kwargs):
    if sender._meta.app_label in _SKIP_APPS or sender._meta.label_lower in _SKIP_MODELS:
        return
    app_label = sender._meta.app_label
    model_name = sender._meta.model_name
    plant_id = _plant_id(instance)
    transaction.on_commit(lambda: _publish(app_label, model_name, "deleted", plant_id))


def _m2m_updated(sender, instance, action, app_label, model_name, field_name, **kwargs):
    if field_name == "target_treatment_plants":
        if instance._meta.model_name in {"treatmentplant", "plant"}:
            plant_ids = (instance.pk,)
        elif action in {"pre_remove", "pre_clear"}:
            pk_set = kwargs.get("pk_set")
            if pk_set is not None:
                plant_ids = tuple(pk_set)
            else:
                plant_ids = tuple(instance.target_treatment_plants.values_list("pk", flat=True))
        elif action == "post_add":
            plant_ids = tuple(kwargs.get("pk_set") or ())
        else:
            plant_ids = ()
        for plant_id in plant_ids:
            transaction.on_commit(
                lambda plant_id=plant_id: _publish(app_label, model_name, "updated", plant_id)
            )
        return
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    plant_id = _plant_id(instance)
    transaction.on_commit(lambda: _publish(app_label, model_name, "updated", plant_id))


def register_realtime_signals():
    """Connect once to concrete models after Django's app registry is ready."""
    for model in apps.get_models(include_auto_created=False):
        if (
            model._meta.abstract
            or model._meta.app_label in _SKIP_APPS
            or model._meta.label_lower in _SKIP_MODELS
        ):
            continue
        dispatch_uid = f"core.live.{model._meta.label_lower}"
        post_save.connect(_saved, sender=model, weak=False, dispatch_uid=f"{dispatch_uid}.save")
        pre_delete.connect(_before_delete, sender=model, weak=False, dispatch_uid=f"{dispatch_uid}.delete")
        for field in model._meta.many_to_many:
            through = field.remote_field.through
            if through._meta.auto_created is not model:
                continue
            m2m_changed.connect(
                lambda sender, instance, action, _app=model._meta.app_label, _name=model._meta.model_name, _field=field.name, **kwargs: _m2m_updated(
                    sender, instance, action, app_label=_app, model_name=_name, field_name=_field, **kwargs
                ),
                sender=through,
                weak=False,
                dispatch_uid=f"{dispatch_uid}.m2m.{field.name}",
            )
