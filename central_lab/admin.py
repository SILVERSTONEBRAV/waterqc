from django.contrib import admin
from .admin_dashboard import CustomAdminSite

admin_site = CustomAdminSite(name='custom_admin')

# Re-register models to the custom admin site
from .models import (
    RegionSample, FCASample, CatchmentSample, KabeteSample, GigiriSample,
    RegionSampleAnalysis, FCASampleAnalysis, CatchmentSampleAnalysis,
    KabeteSampleAnalysis, GigiriSampleAnalysis, SampleCategory
)

admin_site.register(RegionSample)
admin_site.register(FCASample)
admin_site.register(CatchmentSample)
admin_site.register(KabeteSample)
admin_site.register(GigiriSample)
admin_site.register(RegionSampleAnalysis)
admin_site.register(FCASampleAnalysis)
admin_site.register(CatchmentSampleAnalysis)
admin_site.register(KabeteSampleAnalysis)
admin_site.register(GigiriSampleAnalysis)
admin_site.register(SampleCategory)
