# alerts/routing.py
from django.urls import re_path
from .consumers import AlertConsumer

websocket_urlpatterns = [
    # The consumer authorizes a private user group after authentication.
    re_path(r'ws/alerts/$', AlertConsumer.as_asgi()),

    # Optional: per-user streams (can be filtered in consumer by scope.user)
    re_path(r'ws/alerts/(?P<user_id>\d+)/$', AlertConsumer.as_asgi()),
]
