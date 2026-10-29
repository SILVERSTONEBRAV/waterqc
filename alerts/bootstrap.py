import logging
from datetime import timedelta
from django.apps import apps
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


def bootstrap_alerts_system():
    """
    Initializes default VoiceOver profiles, AlertTemplates, AlertCategories,
    and AlertConfigs so that alerts, bell notifications, and voice messages
    are always operational out-of-the-box.
    """
    try:
        User = apps.get_model("accounts", "CustomUser")
        VoiceOver = apps.get_model("alerts", "VoiceOver")
        AlertTemplate = apps.get_model("alerts", "AlertTemplate")
        AlertCategory = apps.get_model("alerts", "AlertCategory")
        AlertConfig = apps.get_model("alerts", "AlertConfig")
    except LookupError as e:
        logger.warning(f"[AlertsBootstrap] Required models not loaded: {e}")
        return

    admin_user = (
        User.objects.filter(is_superuser=True).first()
        or User.objects.first()
    )
    if not admin_user:
        logger.info("[AlertsBootstrap] No user found yet to attach voice over profiles.")
        return

    with transaction.atomic():
        # 1. Ensure default VoiceOver profiles (Slot 1: Martin Nangole, Slot 2: Michael Onyango for 1:1 rotation)
        import os
        from django.conf import settings
        from django.core.files.base import ContentFile

        static_dir = os.path.join(settings.BASE_DIR, "static", "voice_over")
        martin_mp3 = os.path.join(static_dir, "Martin Nangole.mp3")
        michael_mp3 = os.path.join(static_dir, "Michael Onyango.mp3")

        # Resolve or create accounts users for the two supplied voice actors
        martin_user = (
            User.objects.filter(username__icontains="nangole").first()
            or User.objects.filter(first_name__icontains="martin", last_name__icontains="nangole").first()
        )
        if not martin_user:
            martin_user = User.objects.create(
                username="martin.nangole",
                first_name="Martin",
                last_name="Nangole",
                email="mnangole@nairobiwater.co.ke",
                is_active=True,
            )

        michael_user = (
            User.objects.filter(username__icontains="onyango").first()
            or User.objects.filter(first_name__icontains="michael", last_name__icontains="onyango").first()
        )
        if not michael_user:
            michael_user = User.objects.create(
                username="michael.onyango",
                first_name="Michael",
                last_name="Onyango",
                email="monyango@nairobiwater.co.ke",
                is_active=True,
            )

        # Slot 1: Martin Nangole
        v1 = VoiceOver.objects.filter(slot=1).first()
        if not v1:
            v1 = VoiceOver(slot=1)
        v1.name = "Martin Nangole"
        v1.user = martin_user
        v1.gender = "male"
        v1.accent_profile = "co.za"
        v1.speech_rate = 1.0
        v1.is_active = True
        if os.path.exists(martin_mp3):
            with open(martin_mp3, "rb") as f:
                v1.sample_clip.save("Martin_Nangole.mp3", ContentFile(f.read()), save=False)
        v1.save()

        # Slot 2: Michael Onyango
        v2 = VoiceOver.objects.filter(slot=2).first()
        if not v2:
            v2 = VoiceOver(slot=2)
        v2.name = "Michael Onyango"
        v2.user = michael_user
        v2.gender = "male"
        v2.accent_profile = "co.za"
        v2.speech_rate = 1.0
        v2.is_active = True
        if os.path.exists(michael_mp3):
            with open(michael_mp3, "rb") as f:
                v2.sample_clip.save("Michael_Onyango.mp3", ContentFile(f.read()), save=False)
        v2.save()

        # 2. Ensure default Categories
        cat_qc, _ = AlertCategory.objects.get_or_create(
            name="Water Quality Control",
            defaults={"description": "Notifications related to water analysis and sampling parameters."},
        )
        cat_maint, _ = AlertCategory.objects.get_or_create(
            name="Equipment & Maintenance",
            defaults={"description": "Equipment calibration, maintenance, and facility alerts."},
        )

        # 3. Ensure default AlertTemplates
        templates_def = [
            {
                "name": "Water Quality Nonconformity",
                "subject": "Water Quality Nonconformity: {parameter_name}",
                "body": "Quality parameter nonconformity detected: {parameter_name} measured {observed_value} outside limits ({min_limit}–{max_limit}).",
            },
            {
                "name": "Water Analysis Auto Verification",
                "subject": "Water Analysis Verified: {reference_id}",
                "body": "Water analysis {reference_id} has been verified and confirmed within standards.",
            },
            {
                "name": "Equipment Maintenance Due",
                "subject": "Equipment Maintenance Due: {name}",
                "body": "Equipment {name} has scheduled maintenance due. Please perform required servicing.",
            },
            {
                "name": "Equipment Calibration Pending",
                "subject": "Calibration Due: {name}",
                "body": "Equipment {name} calibration is due today. Verification pending.",
            },
            {
                "name": "Scheduled Analysis Generated",
                "subject": "Scheduled Analysis: {reference_id}",
                "body": "A scheduled water analysis batch {reference_id} has been created and awaits testing.",
            },
            {
                "name": "Chemical Workflow Alert",
                "subject": "Chemical Quality Alert",
                "body": "Chemical analysis SLA or quality specification alert requires attention.",
            },
        ]

        template_map = {}
        for tdef in templates_def:
            tmpl, _ = AlertTemplate.objects.get_or_create(
                name=tdef["name"],
                version=1,
                defaults={
                    "subject_template": tdef["subject"],
                    "body_template": tdef["body"],
                    "active": True,
                    "auto_voice_enabled": True,
                },
            )
            template_map[tdef["name"]] = tmpl

        # 4. Ensure default AlertConfigs
        configs_def = [
            {
                "alert_type": "nonconformity",
                "category": cat_qc,
                "priority": "critical",
                "template": template_map["Water Quality Nonconformity"],
            },
            {
                "alert_type": "auto_verification",
                "category": cat_qc,
                "priority": "low",
                "template": template_map["Water Analysis Auto Verification"],
            },
            {
                "alert_type": "maintenance_due",
                "category": cat_maint,
                "priority": "high",
                "template": template_map["Equipment Maintenance Due"],
            },
            {
                "alert_type": "verification_pending",
                "category": cat_maint,
                "priority": "high",
                "template": template_map["Equipment Calibration Pending"],
            },
            {
                "alert_type": "sampling_delay",
                "category": cat_qc,
                "priority": "medium",
                "template": template_map["Scheduled Analysis Generated"],
            },
            {
                "alert_type": "analysis_missed",
                "category": cat_qc,
                "priority": "high",
                "template": template_map["Scheduled Analysis Generated"],
            },
            {
                "alert_type": "ca_assignment_pending",
                "category": cat_qc,
                "priority": "medium",
                "template": template_map["Chemical Workflow Alert"],
                "voice_persistence_mode": AlertConfig.VoicePersistenceMode.UNTIL_ANALYST_ASSIGNED,
            },
            {
                "alert_type": "ca_assignment_escalation",
                "category": cat_qc,
                "priority": "high",
                "template": template_map["Chemical Workflow Alert"],
                "voice_persistence_mode": AlertConfig.VoicePersistenceMode.UNTIL_ANALYST_ASSIGNED,
            },
        ]

        for cdef in configs_def:
            cfg, created = AlertConfig.objects.get_or_create(
                alert_type=cdef["alert_type"],
                defaults={
                    "category": cdef["category"],
                    "priority": cdef["priority"],
                    "template": cdef["template"],
                    "verify_timeout": timedelta(minutes=30),
                    "verify_before_subsequent": timedelta(minutes=15),
                    "approve_timeout": timedelta(minutes=30),
                    "tat_for_escalation": timedelta(hours=1),
                    "escalation_timeout": timedelta(hours=2),
                    "voice_persistence_mode": cdef.get(
                        "voice_persistence_mode",
                        AlertConfig.VoicePersistenceMode.UNTIL_ACKNOWLEDGED,
                    ),
                    "voice_repeat_interval_seconds": 60,
                    "voice_repeat_max_count": 0,
                    "active": True,
                },
            )
            # Ensure admin / all staff users are in recipients
            if created or cfg.recipients.count() == 0:
                cfg.recipients.add(admin_user)

    logger.info("[AlertsBootstrap] Alerts bootstrap successfully finished.")
