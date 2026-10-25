from datetime import date, datetime, time, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.utils import timezone
from django.utils.dateparse import parse_datetime


class DashboardNotificationsView(LoginRequiredMixin, View):
    """Shared dashboard notification feed with enforced plant scope."""

    def get(self, request, *args, **kwargs):
        user = request.user
        from core.engine.super_user import SuperUserEngine
        is_superuser = SuperUserEngine.is_superuser(user)
        plant = self._resolve_plant(request, is_superuser)
        if isinstance(plant, JsonResponse):
            return plant

        alerts = []
        if plant is not None:
            from ca.services.alerts_service import ChemicalAlertsService

            alerts = ChemicalAlertsService.get_user_alerts(
                user=user,
                plant=plant,
                is_superuser=is_superuser,
                limit=25,
            )

        now = timezone.now()
        try:
            from alerts.models import VoiceAlert
            recent_voices = list(VoiceAlert.objects.filter(
                created_at__gte=now - timedelta(days=7)
            ).only("title", "message", "audio_file"))
        except Exception:
            recent_voices = []

        for alert in alerts:
            alert["urgency"] = self._urgency(alert, now)
            alert_type = str(alert.get("type", ""))

            # Guarantee a corresponding voice message for every notification
            title = alert.get("title", "")
            msg = alert.get("message", "")
            match = next((v for v in recent_voices if (v.title and v.title == title) or (v.message and v.message[:30] == msg[:30])), None)
            if match and match.audio_file:
                alert["voice_url"] = match.audio_file.url
            else:
                try:
                    from alerts.models import VoiceAlert
                    new_v = VoiceAlert.generate_persistent_voice_alert(
                        message=f"{title}. {msg}" if title else msg,
                        title=title or "Notification",
                    )
                    if new_v and new_v.audio_file:
                        alert["voice_url"] = new_v.audio_file.url
                        recent_voices.append(new_v)
                except Exception:
                    alert["voice_url"] = None

            if alert_type == "ca_workflow_alert":
                # Durable CA workflow alerts carry a per-recipient decision
                # from the domain service; keep it so only assigned analysts
                # receive an acknowledgement action.
                alert["can_acknowledge"] = bool(alert.get("can_acknowledge"))
            else:
                alert["can_acknowledge"] = alert_type in {
                    "alert_state",
                    "qc_nonconformity",
                    "ca_batch_received",
                    "ca_sla",
                    "ca_out_of_spec",
                    "ca_coa",
                }

        unread = sum(not bool(alert.get("acknowledged")) for alert in alerts)
        response = JsonResponse({
            "success": True,
            "alerts": alerts,
            "unread_count": unread,
            "plant_id": getattr(plant, "pk", None),
            "timestamp": now.isoformat(),
        })
        response["Cache-Control"] = "no-store, max-age=0"
        return response

    @staticmethod
    def _resolve_plant(request, is_superuser):
        from t.models import TreatmentPlant

        if not is_superuser:
            plant = getattr(request.user, "assigned_treatment_plant", None)
            requested = request.GET.get("plant")
            if requested and str(getattr(plant, "pk", "")) != str(requested):
                return JsonResponse({"success": False, "error": "Notification scope is outside your assigned plant."}, status=403)
            return plant or TreatmentPlant.objects.first()

        requested = request.GET.get("plant") or next(
            (
                request.session.get(key)
                for key in (
                    "ca_selected_plant",
                    "qc_selected_plant",
                    "selected_plant_id",
                    "selected_treatment_plant_id",
                    "active_plant_id",
                    "plant_id",
                    "treatment_plant_id",
                )
                if request.session.get(key)
            ),
            None,
        )
        if not requested:
            return getattr(request.user, "assigned_treatment_plant", None) or TreatmentPlant.objects.first()
        if str(requested).casefold() in {"all", "none"}:
            return TreatmentPlant.objects.first()
        if not str(requested).isdigit():
            return TreatmentPlant.objects.first()
        plant = TreatmentPlant.objects.filter(pk=int(requested)).first()
        if plant is None:
            return TreatmentPlant.objects.first()
        return plant

    @staticmethod
    def _urgency(alert, now):
        text = " ".join(str(alert.get(key, "")) for key in ("title", "message", "type")).casefold()
        if any(word in text for word in ("expired", "overdue", "missed", "nonconformity", "out-of-spec", "out of spec", "failed", "rejected")):
            return "expired"
        if any(word in text for word in ("expiring", "due soon")):
            return "almost-expiring"

        severity = str(alert.get("severity", alert.get("priority", ""))).casefold()
        if severity == "critical":
            return "expired"
        if severity == "high":
            return "almost-expiring"

        timestamp = alert.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = parse_datetime(timestamp)
        if isinstance(timestamp, date) and not isinstance(timestamp, datetime):
            timestamp = datetime.combine(timestamp, time.min)
        if timestamp:
            if timezone.is_naive(timestamp):
                timestamp = timezone.make_aware(timestamp, timezone.get_current_timezone())
            if timestamp >= now - timedelta(minutes=60) and not alert.get("acknowledged"):
                return "new"
        if severity == "low":
            return "new"
        return "average"


class DashboardNotificationAckView(LoginRequiredMixin, View):
    """Acknowledge a shared notification after rechecking its scope and access."""

    def post(self, request, alert_id, *args, **kwargs):
        from ca.services.alerts_service import ChemicalAlertsService
        from core.engine.super_user import SuperUserEngine

        is_superuser = SuperUserEngine.is_superuser(request.user)
        plant = DashboardNotificationsView._resolve_plant(request, is_superuser)
        if isinstance(plant, JsonResponse) or plant is None:
            return JsonResponse({"success": False, "error": "Notification not found."}, status=404)

        scoped_alerts = ChemicalAlertsService.get_user_alerts(
            user=request.user,
            plant=plant,
            is_superuser=is_superuser,
            limit=250,
        )
        if not any(str(item.get("id")) == str(alert_id) for item in scoped_alerts):
            return JsonResponse({"success": False, "error": "Notification not found."}, status=404)

        result = ChemicalAlertsService.acknowledge(
            request.user,
            str(alert_id),
            is_superuser=is_superuser,
        )
        response = JsonResponse(result, status=200 if result.get("success") else 404)
        response["Cache-Control"] = "no-store, max-age=0"
        return response
