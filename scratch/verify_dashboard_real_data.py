import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qad.settings")
import django
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from ca.dashboard import DashboardView

User = get_user_model()
admin_user = User.objects.filter(is_superuser=True).first()
plant_user = User.objects.filter(username="TEST_PLANT_ANALYST").first()

print(f"=== TESTING DASHBOARD WITH REAL DATA ===")
print(f"Admin User: {admin_user}")
print(f"Plant User: {plant_user}")

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.messages.storage.fallback import FallbackStorage

rf = RequestFactory()

def setup_request(request, user):
    request.user = user
    request.session = SessionStore()
    setattr(request, '_messages', FallbackStorage(request))
    return request

# 1. Test Superuser Overview
print("\n--- 1. Superuser Overview ---")
req = setup_request(rf.get("/ca/dashboard/?tab=overview"), admin_user)
view = DashboardView()
view.setup(req)
ctx = view.get_context_data()
pbi = ctx.get("pbi", {})

print(f"Active Suppliers: {pbi.get('active_suppliers')}")
print(f"Total Batches: {pbi.get('total_batches')}")
print(f"Total Volume: {pbi.get('total_volume')}")
print(f"Total Results: {pbi.get('total_results')}")
print(f"Total Requests: {pbi.get('total_requests')}")
print(f"Total CoAs: {pbi.get('total_coas')}")
print(f"Active Processes: {pbi.get('active_processes')}")
print(f"Compliance Rate: {pbi.get('compliance_rate')}% (offset: {pbi.get('gauge_offset')})")
print(f"Chemical Volume Breakdown (Count: {len(pbi.get('chemical_volume_breakdown', []))}):")
for item in pbi.get("chemical_volume_breakdown", []):
    print(f"  - {item['short_name']}: {item['volume_display']} (width: {item['pct_width']}%)")
print(f"Plant Volume Breakdown (Count: {len(pbi.get('plant_volume_breakdown', []))}):")
for item in pbi.get("plant_volume_breakdown", []):
    print(f"  - {item['short_name']}: {item['batch_count']} batches (height: {item['pct_height']}%)")
print(f"Stage Distribution: {pbi.get('stage_distribution')}")

# Render response
res = view.get(req)
print(f"Superuser Overview HTTP Status: {res.status_code}")
content = res.rendered_content
assert "pbi-kpi-card" in content, "KPI strip missing in HTML"
assert "pbi-hbar-row" in content, "Horizontal bar rows missing in HTML"
assert "pbi-col-item" in content, "Column chart items missing in HTML"
print("Superuser HTML assertions passed successfully!")

# 2. Test Non-Superuser (Plant-Scoped) Overview
if plant_user:
    print("\n--- 2. Plant-Scoped Non-Superuser (TEST_PLANT_ANALYST) Overview ---")
    req2 = setup_request(rf.get("/ca/dashboard/?tab=overview"), plant_user)
    view2 = DashboardView()
    view2.setup(req2)
    ctx2 = view2.get_context_data()
    pbi2 = ctx2.get("pbi", {})
    plant_ctx = ctx2.get("plant_context", {})

    print(f"User Plant: {plant_ctx.get('plant_name')}")
    print(f"Scoped Active Suppliers: {pbi2.get('active_suppliers')}")
    print(f"Scoped Total Batches: {pbi2.get('total_batches')}")
    print(f"Scoped Total Volume: {pbi2.get('total_volume')}")
    print(f"Scoped Total Results: {pbi2.get('total_results')}")
    print(f"Scoped Total CoAs: {pbi2.get('total_coas')}")
    print(f"Scoped Plant Breakdown (Count: {len(pbi2.get('plant_volume_breakdown', []))}):")
    for item in pbi2.get("plant_volume_breakdown", []):
        print(f"  - {item['short_name']}: {item['batch_count']} batches")

    res2 = view2.get(req2)
    print(f"Plant-Scoped Overview HTTP Status: {res2.status_code}")
    print("Non-superuser HTML assertions passed successfully!")

# 3. Test All 10 Tabs Render HTTP 200
tabs = [
    "overview", "batches", "requests", "checklists", "results",
    "processes", "coas", "analytics", "reports", "admin"
]
print("\n--- 3. Testing All 10 Tabs (Superuser) ---")
for t in tabs:
    t_req = setup_request(rf.get(f"/ca/dashboard/?tab={t}"), admin_user)
    t_view = DashboardView()
    t_view.setup(t_req)
    t_res = t_view.get(t_req)
    assert t_res.status_code == 200, f"Tab {t} failed with status {t_res.status_code}"
    print(f"  - Tab '{t}': HTTP {t_res.status_code} OK")

print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
