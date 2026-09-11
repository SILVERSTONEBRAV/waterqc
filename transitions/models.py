from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class AnalysisStates(models.TextChoices):
    NEW = 'new', _('New')
    ANALYSED = 'analysed', _('Analysed')
    VERIFIED = 'verified', _('Verified')
    CONFIRMED = 'confirmed', _('Confirmed')
    APPROVED = 'approved', _('Approved')


class StateTransitionLog(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = models.GenericForeignKey()
    new_state = models.CharField(max_length=20)
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        user_str = self.user.get_full_name() if self.user else "System"
        return f"{self.content_type}:{self.object_id} → {self.new_state} by {user_str} @ {self.timestamp:%Y-%m-%d %H:%M}"


class StateMixin(models.Model):
    state = models.CharField(max_length=20, choices=AnalysisStates.choices, default=AnalysisStates.NEW)
    transitions = GenericRelation(StateTransitionLog, related_query_name="transitions")

    class Meta:
        abstract = True

    STATE_TRANSITIONS = {}
    STATE_PERMISSIONS = {}
    STATE_USER_FIELD = {}

    def transition_state(self, new_state: str, user: User):
        allowed = self.STATE_TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            raise ValidationError(f"Invalid transition from '{self.state}' to '{new_state}'.")

        required_perm = self.STATE_PERMISSIONS.get(new_state)
        if required_perm and not user.has_perm(required_perm):
            raise PermissionDenied(f"User lacks permission '{required_perm}'.")

        user_field = self.STATE_USER_FIELD.get(new_state)
        if user_field:
            setattr(self, user_field, user)

        self.state = new_state
        self.save()
