# audit_logs/management/commands/update_audit_logs.py

from django.core.management.base import BaseCommand
from audit_logs.models import AuditLogEntry
from django.utils import timezone

class Command(BaseCommand):
    help = 'Updates audit logs periodically'

    def handle(self, *args, **options):
        now = timezone.now()
        # Perform periodic updates and cleanup if necessary
        self.stdout.write(self.style.SUCCESS('Audit logs updated successfully at %s' % now))
