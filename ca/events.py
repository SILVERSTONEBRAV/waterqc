#events.py
from django.dispatch import Signal
from .middleware import get_current_user

batch_status_changed = Signal()
request_status_changed = Signal()
checklist_completed = Signal()

def audit_signal_handler(sender, instance, old_status, new_status, performed_by=None, **kwargs):
    user = performed_by or get_current_user() or "SYSTEM"
    # Save an AuditLog object or just print
    from .models_audit import AuditLog  # if you have a dedicated table
    AuditLog.objects.create(
        entity=str(instance),
        model=instance.__class__.__name__,
        old_status=old_status,
        new_status=new_status,
        performed_by=user if isinstance(user, str) else user.username,
    )

batch_status_changed.connect(audit_signal_handler)
request_status_changed.connect(audit_signal_handler)
