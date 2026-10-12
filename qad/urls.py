#qad/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

import os
from core.views import HomeView
from accounts.LoginView import LoginView
from accounts.LogoutView import LogoutView


def manifest_json(request):
    manifest_path = os.path.join(settings.BASE_DIR, 'static', 'manifest.json')
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        content = '{}'
    return HttpResponse(content, content_type='application/manifest+json')


def service_worker(request):
    sw_path = os.path.join(settings.BASE_DIR, 'core', 'static', 'core', 'js', 'sw.js')
    try:
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        content = ''
    response = HttpResponse(content, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('manifest.json', manifest_json, name='pwa_manifest'),
    path('sw.js', service_worker, name='pwa_service_worker'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
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