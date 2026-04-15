from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from django.core.cache import cache
from urllib.parse import parse_qs

User = get_user_model()


@database_sync_to_async
def get_user_from_ticket(ticket):
    cache_key = f"ws_ticket_{ticket}"
    user_id = cache.get(cache_key)

    if user_id:
        cache.delete(cache_key)
        try:
            return User.objects.only('id', 'username', 'roles').get(pk=user_id)
        except User.DoesNotExist:
            return AnonymousUser()
    return AnonymousUser()


class TicketAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        ticket = query_params.get("ticket", [None])[0]

        if ticket:
            scope['user'] = await get_user_from_ticket(ticket)
        else:
            scope['user'] = AnonymousUser()

        return await self.app(scope, receive, send)
