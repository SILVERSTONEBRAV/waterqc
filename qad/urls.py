#qad/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

from core.views import HomeView


urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('core/', include('core.urls')),
    path('admin/', admin.site.urls),
    path('qca/', include('qc_analytics.urls')),
    path('accounts/', include('accounts.urls')),
    path("ca/", include("ca.urls")),
    path('t/', include('t.urls')),
    path('inventory/', include('inventory.urls')),
    path("sc/", include("sc.urls")),
    path('wc/', include('wc.urls')),
    path('parameters/', include('parameters.urls')),
    path('microbial/', include('microbial.urls')),
    path("heavy_metal/", include("heavy_metal.urls")),
    path('instruments/', include('instruments.urls')),
    path('o/', include('o.urls')),
    path('PHadjustment/', include('PHadjustment.urls')),
    path("duty_house/", include("duty_house.urls")),
    path('wsp/', include('wsp.urls')),
    path('maintenance/', include('maintenance.urls')),
    path("Maintenance_Incident/", include("Maintenance_Incident.urls")),
    path('chlorinedemand/', include('chlorinedemand.urls')),
    path("jartest/", include("jartest.urls")),
    path('destw/', include('destw.urls')),
    path('kstw/', include('kstw.urls')),
    path('backwashing/', include('backwashing.urls')),
    path('weeklytasks/', include('weeklytasks.urls')),
    path('xmicalconcentration/', include('xmicalconcentration.urls')),
    path("itinerary/", include("itinerary.urls")),
    path('filtered_water/', include('filtered_water.urls')),
    path('CompanyInfo/', include('CompanyInfo.urls')),
    path("alerts/", include("alerts.urls")),
    path('central_lab/', include('central_lab.urls')),
    path('qc/', include('qc.urls')),
    path("health/", lambda request: HttpResponse("OK"), name="health",),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )