from django.urls import re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

from .consumers import MQTTConsumer

# ==============================
# WebSocket URL patterns
# ==============================
websocket_urlpatterns = [
    # Instruments connect via WebSocket bridge for MQTT messages
    re_path(r'ws/mqtt/$', MQTTConsumer.as_asgi()),
]

# ==============================
# Channels Protocol Router
# ==============================
application = ProtocolTypeRouter({
    # WebSocket connections are wrapped with auth middleware
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})
