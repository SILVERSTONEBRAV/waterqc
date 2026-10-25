from django.urls import re_path

from .consumers import DashboardConsumer
from core.live_consumer import LiveUpdateConsumer

websocket_urlpatterns = [
    re_path(r"^ws/live/$", LiveUpdateConsumer.as_asgi(), name="live-updates"),
    re_path(
        r"^ws/qc/dashboard/$",
        DashboardConsumer.as_asgi(),
        name="qc-dashboard",
    ),
]
