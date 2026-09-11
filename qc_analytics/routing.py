# qc_analytics/routing.py
from django.urls import re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from .consumers import QCAnalyticsConsumer

# ---------------------------------------------------------
# WebSocket URL patterns
# ---------------------------------------------------------
websocket_urlpatterns = [
    # 🌐 Global QC analytics feed
    re_path(r"ws/qc/analytics/$", QCAnalyticsConsumer.as_asgi()),

    # 🏭 Plant-specific feed (optional plant_id)
    re_path(
        r"ws/qc/analytics/plant/(?P<plant_id>\d+)/$",
        QCAnalyticsConsumer.as_asgi(),
    ),

    # 🏭 Phase-specific feed within a plant (plant_id + phase)
    re_path(
        r"ws/qc/analytics/plant/(?P<plant_id>\d+)/phase/(?P<phase>[a-zA-Z0-9_-]+)/$",
        QCAnalyticsConsumer.as_asgi(),
    ),

    # 🔄 Multi-parameter comparison (comma-separated)
    re_path(
        r"ws/qc/analytics/compare/(?P<parameters>[\w,]+)/$",
        QCAnalyticsConsumer.as_asgi(),
    ),

    # 📊 Historical range analytics (start/end via query string)
    re_path(
        r"ws/qc/analytics/historical/$",
        QCAnalyticsConsumer.as_asgi(),
    ),

    # ⚠️ Alerts feed (optional future extension)
    re_path(
        r"ws/qc/analytics/alerts/$",
        QCAnalyticsConsumer.as_asgi(),
    ),

    # 📄 PDF report notifications (optional future extension)
    re_path(
        r"ws/qc/analytics/reports/$",
        QCAnalyticsConsumer.as_asgi(),
    ),
]

# ---------------------------------------------------------
# Protocol type router
# ---------------------------------------------------------
application = ProtocolTypeRouter({
    # 🔐 WebSocket connections
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})

# ---------------------------------------------------------
# Notes / Features
# ---------------------------------------------------------
# 1️⃣ AllowedHostsOriginValidator: Prevents unauthorized cross-origin WS connections.
# 2️⃣ AuthMiddlewareStack: Automatically attaches user info to scope.
# 3️⃣ Dynamic URL patterns:
#     - Global dashboards: /ws/qc/analytics/
#     - Plant dashboards: /ws/qc/analytics/plant/<plant_id>/
#     - Phase dashboards: /ws/qc/analytics/plant/<plant_id>/phase/<phase>/
#     - Multi-parameter comparisons: /ws/qc/analytics/compare/<param1,param2,...>/
#     - Historical range analytics: /ws/qc/analytics/historical/?start=YYYY-MM-DD&end=YYYY-MM-DD
#     - Alerts: /ws/qc/analytics/alerts/
#     - Reports: /ws/qc/analytics/reports/
# 4️⃣ Extensible for future analytics feeds:
#     - Additional groups can be added dynamically in the consumer
#     - PDF generation or anomaly alerts can push updates here
# 5️⃣ Supports selective broadcasting:
#     - Consumers join groups dynamically using scope parameters (plant_id, phase, parameters)
#     - Enables real-time filtered dashboards per plant/phase
