# ca/views/dashboard_ws.py
from django.shortcuts import render
from django.views import View
from django.http import JsonResponse
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Count, Q, F, Avg, ExpressionWrapper, DurationField, FloatField
from django.db.models.functions import TruncDate, Cast
from datetime import timedelta
from django.contrib.auth import get_user_model

from .models import ChemicalBatch, ChemicalAnalysisRequest, ChemicalCoA

User = get_user_model()


class DashboardView(View):
    CACHE_TIMEOUT = 60  # seconds
    DAYS = 30

    def get_base_data(self):
        """Compute all metrics and tables with optimized queries."""
        now = timezone.now()
        today = now.date()
        start_date = today - timedelta(days=self.DAYS - 1)

        batches_qs = ChemicalBatch.objects.all()
        requests_qs = ChemicalAnalysisRequest.objects.all()
        coas_qs = ChemicalCoA.objects.select_related("batch")

        # ---------------- BATCH METRICS ----------------
        batch_stats = batches_qs.aggregate(
            total=Count("id"),
            approved=Count("id", filter=Q(status=ChemicalBatch.Status.APPROVED)),
            rejected=Count("id", filter=Q(status=ChemicalBatch.Status.REJECTED)),
        )
        pending_batches = batch_stats["total"] - batch_stats["approved"] - batch_stats["rejected"]

        # ---------------- REQUEST METRICS ----------------
        request_stats = requests_qs.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=ChemicalAnalysisRequest.Status.COMPLETED)),
            overdue=Count(
                "id",
                filter=Q(
                    status__in=[ChemicalAnalysisRequest.Status.PENDING, ChemicalAnalysisRequest.Status.IN_PROGRESS],
                    analysis_deadline__lt=now
                )
            ),
        )

        # ---------------- SLA & RISK ENGINE ----------------
        avg_completed_duration = requests_qs.filter(
            status=ChemicalAnalysisRequest.Status.COMPLETED,
            analysis_started_at__isnull=False
        ).annotate(
            duration=ExpressionWrapper(F("updated_at") - F("analysis_started_at"), output_field=DurationField())
        ).aggregate(avg_duration=Avg("duration"))["avg_duration"]
        avg_hours = avg_completed_duration.total_seconds()/3600 if avg_completed_duration else 9

        active_requests = requests_qs.filter(
            status__in=[ChemicalAnalysisRequest.Status.PENDING, ChemicalAnalysisRequest.Status.IN_PROGRESS],
            analysis_deadline__isnull=False
        ).annotate(
            hours_left=ExpressionWrapper(F("analysis_deadline") - now, output_field=DurationField()),
            risk_score=ExpressionWrapper(
                Cast(avg_hours, FloatField()) /
                Cast(F("analysis_deadline") - now, FloatField()),
                output_field=FloatField()
            ),
            sla_flag=Q(
                status=ChemicalAnalysisRequest.Status.COMPLETED,
                updated_at__lte=F("analysis_deadline")
            ) | Q(
                status__in=[ChemicalAnalysisRequest.Status.PENDING, ChemicalAnalysisRequest.Status.IN_PROGRESS],
                analysis_deadline__gte=now
            )
        ).aggregate(
            risk_count=Count("id", filter=Q(risk_score__gt=1.2)),
            risk_index=Avg("risk_score", filter=Q(risk_score__gt=1.2)),
            sla_on_time=Count("id", filter=Q(sla_flag=True))
        )

        risk_count = active_requests["risk_count"] or 0
        risk_index = round(active_requests["risk_index"] or 0, 2)
        sla_on_time = active_requests["sla_on_time"]
        sla_total = requests_qs.filter(
            status__in=[ChemicalAnalysisRequest.Status.COMPLETED,
                        ChemicalAnalysisRequest.Status.PENDING,
                        ChemicalAnalysisRequest.Status.IN_PROGRESS]
        ).count()
        sla_compliance = int((sla_on_time / sla_total) * 100) if sla_total else 100

        # ---------------- TIMESERIES ----------------
        def timeseries(qs, field):
            data = (
                qs.filter(**{f"{field}__date__gte": start_date})
                  .annotate(day=TruncDate(field))
                  .values("day")
                  .annotate(count=Count("id"))
            )
            mapping = {d["day"]: d["count"] for d in data}
            return [mapping.get(start_date + timedelta(days=i), 0) for i in range(self.DAYS)]

        batch_trend = timeseries(batches_qs, "created_at")
        request_trend = timeseries(requests_qs, "created_at")

        # ---------------- WORKLOAD ----------------
        analyst_count = User.objects.filter(groups__name="Analyst").count() or 1
        workload = round(
            requests_qs.filter(status__in=[ChemicalAnalysisRequest.Status.PENDING, ChemicalAnalysisRequest.Status.IN_PROGRESS]).count()
            / analyst_count,
            2
        )

        # ---------------- TABLE DATA ----------------
        tables = {
            "batches": list(batches_qs.order_by("-created_at")[:20].values("id", "sample_id", "status", "received_date")),
            "requests": list(requests_qs.order_by("-created_at")[:20].values("id", "request_id", "status", "analysis_deadline")),
            "coas": list(coas_qs.order_by("-date_of_report")[:20].values("id", "batch__sample_id", "date_of_report")),
        }

        # ---------------- FINAL PAYLOAD ----------------
        payload = {
            "generated_at": now,
            "cards": [
                {"label": "Total Batches", "value": batch_stats["total"], "trend": batch_trend},
                {"label": "Approved", "value": batch_stats["approved"]},
                {"label": "Rejected", "value": batch_stats["rejected"]},
                {"label": "Pending", "value": pending_batches},
                {"label": "Requests", "value": request_stats["total"], "trend": request_trend},
                {"label": "Completed", "value": request_stats["completed"]},
                {"label": "Overdue", "value": request_stats["overdue"]},
                {"label": "SLA Compliance", "value": sla_compliance, "unit": "%"},
                {"label": "Risk Count", "value": risk_count},
                {"label": "Risk Index", "value": risk_index},
                {"label": "Workload / Analyst", "value": workload},
            ],
            "tables": tables
        }

        return payload

    def get(self, request):
        """Render HTML dashboard or return JSON if requested via AJAX/WebSocket."""
        if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("format") == "json":
            payload = self.get_base_data()
            return JsonResponse(payload, safe=False)

        # Cache for regular HTML rendering
        cache_key = "dashboard_ws_html"
        cached = cache.get(cache_key)
        if cached:
            return render(request, "ca/dashboard.html", cached)

        payload = self.get_base_data()
        cache.set(cache_key, payload, self.CACHE_TIMEOUT)
        return render(request, "ca/dashboard.html", payload)
