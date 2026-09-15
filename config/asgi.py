import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_application = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from apps.notifications.middleware import TicketAuthMiddleware
from apps.notifications.routing import websocket_urlpatterns as notification_ws_urls
from apps.projects.routing import websocket_urlpatterns as project_ws_urls

application = ProtocolTypeRouter({
    "http": django_application,
    "websocket": TicketAuthMiddleware(
        URLRouter(
            notification_ws_urls + project_ws_urls
        )
    ),
})
