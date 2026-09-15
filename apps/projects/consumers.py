from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.cache import cache
from apps.projects.models import Meeting
from apps.projects.services import LiveKitService
from apps.users.models import Role


class MeetingConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or self.user.is_anonymous:
            await self.accept()
            await self.send_json({
                "type": "error",
                "code": 401,
                "message": "Autentifikatsiyadan o'tilmagan."
            })
            await self.close(code=4003)
            return

        self.meeting_id = self.scope['url_route']['kwargs'].get('meeting_id')
        self.meeting = await self.get_meeting(self.meeting_id)

        if not self.meeting or self.meeting.is_completed or not self.meeting.is_active:
            await self.accept()
            await self.send_json({
                "type": "error",
                "code": 404,
                "message": "Ushbu yig'ilish allaqachon tugagan yoki mavjud emas."
            })
            await self.close(code=4004)
            return

        is_allowed = await self.check_user_permission(self.user, self.meeting)
        if not is_allowed:
            await self.accept()
            await self.send_json({
                "type": "error",
                "code": 403,
                "message": "Siz ushbu yig'ilish qatnashchisi emassiz."
            })
            await self.close(code=4003)
            return

        self.room_group = f"meeting_{self.meeting_id}"
        self.user_group = f"meeting_{self.meeting_id}_user_{self.user.id}"

        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.channel_layer.group_add(self.user_group, self.channel_name)

        is_host = await self.is_host_or_admin(self.user, self.meeting)
        if is_host:
            self.hosts_group = f"meeting_{self.meeting_id}_hosts"
            await self.channel_layer.group_add(self.hosts_group, self.channel_name)

        await self.accept()

        organizer_joined = await self.is_organizer_joined(self.meeting)
        is_approved = await self.get_approval_status(self.meeting.id, self.user.id)

        token = None
        if is_host or is_approved or (not self.meeting.requires_approval and organizer_joined):
            token = await self.get_livekit_token(self.user.id, self.meeting)

        await self.send_json({
            "type": "meeting_state",
            "meeting_id": self.meeting.id,
            "title": self.meeting.title,
            "requires_approval": self.meeting.requires_approval,
            "organizer_joined": organizer_joined,
            "is_host": is_host,
            "is_approved": bool(is_approved or is_host),
            "token": token,
            "server_url": settings.LIVEKIT_URL if token else None,
            "room_name": self.meeting.uid if token else None
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group'):
            await self.channel_layer.group_discard(self.room_group, self.channel_name)
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, 'hosts_group'):
            await self.channel_layer.group_discard(self.hosts_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get('action')

        if action == 'ask_to_join':
            await self.handle_ask_to_join(content)
        elif action == 'admit':
            await self.handle_admit(content)
        elif action == 'get_token':
            await self.handle_get_token()

    async def handle_get_token(self):
        fresh_meeting = await self.get_meeting(self.meeting_id)
        if fresh_meeting:
            self.meeting = fresh_meeting
        is_host = await self.is_host_or_admin(self.user, self.meeting)
        if not is_host:
            organizer_joined = await self.is_organizer_joined(self.meeting)
            if not organizer_joined:
                await self.send_json({
                    "type": "token_response",
                    "status": "waiting",
                    "message": "Tashkilotchi yig'ilishga kirmaguncha kuting."
                })
                return

            if self.meeting.requires_approval:
                is_approved = await self.get_approval_status(self.meeting.id, self.user.id)
                if not is_approved:
                    await self.send_json({
                        "type": "token_response",
                        "status": "waiting_approval",
                        "message": "Tashkilotchi tasdiqlashini kuting."
                    })
                    return

        token = await self.get_livekit_token(self.user.id, self.meeting)
        await self.send_json({
            "type": "token_response",
            "status": "joined",
            "server_url": settings.LIVEKIT_URL,
            "room_name": self.meeting.uid,
            "token": token
        })

    async def handle_ask_to_join(self, content):
        avatar_url = None
        if hasattr(self.user, 'avatar') and self.user.avatar:
            try:
                avatar_url = self.user.avatar.url
            except Exception:
                avatar_url = None

        knock_data = {
            "type": "knock_request",
            "meeting_id": self.meeting.id,
            "user_id": self.user.id,
            "username": self.user.username,
            "avatar": avatar_url,
        }

        hosts_group = f"meeting_{self.meeting_id}_hosts"
        await self.channel_layer.group_send(
            hosts_group,
            {
                "type": "knock_request",
                "data": knock_data
            }
        )
        organizer_group = f"meeting_{self.meeting_id}_user_{self.meeting.organizer_id}"
        await self.channel_layer.group_send(
            organizer_group,
            {
                "type": "knock_request",
                "data": knock_data
            }
        )

    async def handle_admit(self, content):
        is_host = await self.is_host_or_admin(self.user, self.meeting)
        if not is_host:
            await self.send_json({"error": "Faqat mezbon ruxsat bera oladi."})
            return

        target_user_id = content.get('user_id')
        decision = content.get('decision', 'reject')

        target_group = f"meeting_{self.meeting_id}_user_{target_user_id}"

        if decision == 'approve':
            token = await self.get_livekit_token(target_user_id, self.meeting)
            await self.set_approval_cache(self.meeting.id, target_user_id)

            await self.channel_layer.group_send(
                target_group,
                {
                    "type": "knock_response",
                    "data": {
                        "type": "knock_response",
                        "status": "approved",
                        "server_url": settings.LIVEKIT_URL,
                        "room_name": self.meeting.uid,
                        "token": token
                    }
                }
            )
        else:
            await self.channel_layer.group_send(
                target_group,
                {
                    "type": "knock_response",
                    "data": {
                        "type": "knock_response",
                        "status": "rejected",
                        "message": "Mezbon yig'ilishga kirishingizni rad etdi."
                    }
                }
            )

    async def knock_request(self, event):
        await self.send_json(event['data'])

    async def knock_response(self, event):
        await self.send_json(event['data'])

    async def meeting_broadcast(self, event):
        data = event.get('data', {})
        if data.get('type') == 'organizer_joined':
            if not self.meeting.requires_approval and self.user.id != self.meeting.organizer_id:
                token = await self.get_livekit_token(self.user.id, self.meeting)
                await self.send_json({
                    "type": "token_response",
                    "status": "joined",
                    "server_url": settings.LIVEKIT_URL,
                    "room_name": self.meeting.uid,
                    "token": token
                })
        await self.send_json(data)

    @database_sync_to_async
    def get_meeting(self, meeting_id):
        return Meeting.objects.filter(id=meeting_id).select_related('project', 'organizer').first()

    @database_sync_to_async
    def check_user_permission(self, user, meeting):
        if meeting.organizer_id == user.id:
            return True
        return meeting.participants.filter(id=user.id).exists()

    @database_sync_to_async
    def is_host_or_admin(self, user, meeting):
        if meeting.organizer_id == user.id:
            return True
        is_participant = meeting.participants.filter(id=user.id).exists()
        if is_participant and (
            user.is_superuser or
            user.has_role(Role.ADMIN) or
            (meeting.project and meeting.project.manager_id == user.id)
        ):
            return True
        return False

    @database_sync_to_async
    def is_organizer_joined(self, meeting):
        from apps.projects.models import MeetingAttendance
        return MeetingAttendance.objects.filter(
            meeting=meeting,
            user_id=meeting.organizer_id,
            is_attended=True
        ).exists()

    @database_sync_to_async
    def get_approval_status(self, meeting_id, user_id):
        return bool(cache.get(f"meeting_{meeting_id}_approved_{user_id}"))

    @database_sync_to_async
    def get_livekit_token(self, user_id, meeting):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        target_user = User.objects.get(id=user_id)
        return LiveKitService.generate_token(target_user, meeting)

    @database_sync_to_async
    def set_approval_cache(self, meeting_id, user_id):
        cache.set(f"meeting_{meeting_id}_approved_{user_id}", True, timeout=86400)
