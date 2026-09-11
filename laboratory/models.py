#laboratory/models.py
import string
import random
from django.db import models
from django.utils import timezone
from django.apps import apps

# laboratory/models.py

from django.contrib.auth import get_user_model

class Laboratory(models.Model):
    name = models.CharField(max_length=100)
    treatment_plant = models.OneToOneField('t.TreatmentPlant', related_name='laboratory', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.treatment_plant.name}"

    def get_lab_users(self):
        User = get_user_model()
        return self.users.select_related('treatment_plant').prefetch_related('groups').all()

    def get_lab_user_roles(self):
        """Returns a list of tuples: (user, [group names])"""
        return [(user, [group.name for group in user.groups.all()]) for user in self.get_lab_users()]
