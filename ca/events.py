"""Domain event signals for the chemical analysis module."""

from django.dispatch import Signal

batch_status_changed = Signal()
request_status_changed = Signal()
checklist_completed = Signal()

