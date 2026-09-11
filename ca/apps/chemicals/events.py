# apps/chemicals/events.py
from django.dispatch import Signal

batch_status_changed = Signal()
request_status_changed = Signal()
checklist_completed = Signal()
