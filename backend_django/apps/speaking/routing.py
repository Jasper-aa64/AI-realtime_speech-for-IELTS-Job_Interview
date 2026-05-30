from __future__ import annotations

from django.urls import path

from .consumers import RealtimePingConsumer


websocket_urlpatterns = [
    path("ws/realtime/ping/", RealtimePingConsumer.as_asgi()),
]
