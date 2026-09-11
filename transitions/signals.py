from django.db.models.signals import post_save
from django.dispatch import receiver
from transitions.models import StateTransitionLog, StateMixin
from django.contrib.contenttypes.models import ContentType

# Track previous state values
_previous_states = {}


@receiver(post_save)
def track_state_transition(sender, instance, created, **kwargs):
    if not issubclass(sender, StateMixin) or created:
        return

    prev_state = _previous_states.pop(instance.pk, None)
    if prev_state and instance.state != prev_state:
        StateTransitionLog.objects.create(
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.pk,
            new_state=instance.state,
            user=getattr(instance, 'modified_by', None)  # requires convention or override
        )


def cache_previous_state(sender, instance, **kwargs):
    if isinstance(instance, StateMixin):
        _previous_states[instance.pk] = instance.state


def connect_signals():
    from django.db.models.signals import pre_save
    pre_save.connect(cache_previous_state, dispatch_uid="cache_prev_state")
    post_save.connect(track_state_transition, dispatch_uid="log_state_transition")
