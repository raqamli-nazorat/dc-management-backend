import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        cache_key = self.scope.get('ws_cache_key')

        if not user or user.is_anonymous:
            await self.close(code=4003)
            return

        await self.accept()

        if cache_key:
            cache.delete(cache_key)

        self.group_name = f"user_{user.id}_notifications"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def send_notification(self, event):
        message = event['message']
        await self.send(text_data=json.dumps(message))
