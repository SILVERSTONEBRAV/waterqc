from django.db.models.signals import post_save
from django.dispatch import receiver
from raw_water.models import RawWater
from treated_water.models import TreatedWater
from coagulated_water.models import CoagulatedWater
from clarified_water.models import ClarifiedWater
from filtered_water.models import FilteredWater
from nonconformity.models import Nonconformity
from alerts.utils import trigger_alert

@receiver(post_save, sender=RawWater)
def handle_raw_water_save(sender, instance, created, **kwargs):
    if created:
        trigger_alert('new_sample_added', instance)

@receiver(post_save, sender=TreatedWater)
def handle_treated_water_save(sender, instance, created, **kwargs):
    if created:
        trigger_alert('new_sample_added', instance)

@receiver(post_save, sender=CoagulatedWater)
def handle_coagulated_water_save(sender, instance, created, **kwargs):
    if created:
        trigger_alert('new_sample_added', instance)

@receiver(post_save, sender=ClarifiedWater)
def handle_clarified_water_save(sender, instance, created, **kwargs):
    if created:
        trigger_alert('new_sample_added', instance)

@receiver(post_save, sender=FilteredWater)
def handle_filtered_water_save(sender, instance, created, **kwargs):
    if created:
        trigger_alert('new_sample_added', instance)
