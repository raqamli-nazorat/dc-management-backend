from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from django.core.cache import cache
from urllib.parse import parse_qs

User = get_user_model()


@database_sync_to_async
def get_user_and_cache_key(ticket):
    cache_key = f"ws_ticket_{ticket}"
    user_id = cache.get(cache_key)

    if user_id:
        try:
            user = User.objects.only('id', 'username').get(pk=user_id)
            return user, cache_key
        except User.DoesNotExist:
            return AnonymousUser(), None
    return AnonymousUser(), None


class TicketAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        ticket = query_params.get("ticket", [None])[0]

        if ticket:
            user, cache_key = await get_user_and_cache_key(ticket)
            scope['user'] = user
            scope['ws_cache_key'] = cache_key
        else:
            scope['user'] = AnonymousUser()
            scope['ws_cache_key'] = None

        return await self.app(scope, receive, send)
