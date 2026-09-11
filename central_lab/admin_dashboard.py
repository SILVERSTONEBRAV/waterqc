from django.contrib.admin import AdminSite
from django.urls import path
from django.template.response import TemplateResponse
from django.db.models import Count, Avg, Q
from .models import (
    RegionSample, FCASample, CatchmentSample, KabeteSample, GigiriSample,
    RegionSampleParameterResult, FCASampleParameterResult, CatchmentSampleParameterResult,
    KabeteSampleParameterResult, GigiriSampleParameterResult, SampleCategory
)

class CustomAdminSite(AdminSite):
    index_template = 'admin/custom_index.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(self.dashboard_view), name="custom-dashboard"),
        ]
        return custom_urls + urls

    def dashboard_view(self, request):
        # Sample Counts
        sample_counts = {
            'region_samples': RegionSample.objects.filter(is_deleted=False).count(),
            'fca_samples': FCASample.objects.filter(is_deleted=False).count(),
            'catchment_samples': CatchmentSample.objects.filter(is_deleted=False).count(),
            'kabete_samples': KabeteSample.objects.filter(is_deleted=False).count(),
            'gigiri_samples': GigiriSample.objects.filter(is_deleted=False).count(),
        }

        # Compliance Rates
        compliance_stats = {
            'region_compliance': RegionSampleParameterResult.objects.aggregate(average=Avg(QualityComplianceNumeric())),
            'fca_compliance': FCASampleParameterResult.objects.aggregate(average=Avg(QualityComplianceNumeric())),
            'catchment_compliance': CatchmentSampleParameterResult.objects.aggregate(average=Avg(QualityComplianceNumeric())),
            'kabete_compliance': KabeteSampleParameterResult.objects.aggregate(average=Avg(QualityComplianceNumeric())),
            'gigiri_compliance': GigiriSampleParameterResult.objects.aggregate(average=Avg(QualityComplianceNumeric())),
        }

        # Latest Samples (limit 5)
        latest_samples = RegionSample.objects.filter(is_deleted=False).order_by('-sampling_date')[:5]

        context = dict(
            self.each_context(request),
            sample_counts=sample_counts,
            compliance_stats=compliance_stats,
            latest_samples=latest_samples,
        )
        return TemplateResponse(request, "admin/custom_dashboard.html", context)

# Helper to convert Compliance String to Numeric (Complying=1, Not Complying=0)
from django.db.models import Case, When, IntegerField

def QualityComplianceNumeric():
    return Case(
        When(quality_compliance='Complying', then=1),
        When(quality_compliance='Not Complying', then=0),
        default=None,
        output_field=IntegerField()
    )
