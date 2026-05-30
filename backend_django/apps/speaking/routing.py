from __future__ import annotations

from django.urls import path

from .consumers import RealtimePcmUplinkConsumer, RealtimePingConsumer


websocket_urlpatterns = [
    path("ws/realtime/ping/", RealtimePingConsumer.as_asgi()),
    path("ws/realtime/pcm/", RealtimePcmUplinkConsumer.as_asgi()),
]
