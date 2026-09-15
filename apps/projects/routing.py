from django.urls import re_path
from .consumers import MeetingConsumer

websocket_urlpatterns = [
    re_path(r'^(?:api/)?ws/meetings/(?P<meeting_id>\d+)/?$', MeetingConsumer.as_asgi()),
]
