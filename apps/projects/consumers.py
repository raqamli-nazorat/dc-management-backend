import json
import uuid
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.projects.models import Meeting
from apps.projects.services import LiveKitService
from apps.users.models import Role


class MeetingConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or self.user.is_anonymous:
            await self.accept()
            await self.send_json(
                {
                    "type": "error",
                    "code": 401,
                    "message": "Autentifikatsiyadan o'tilmagan.",
                }
            )
            await self.close(code=4003)
            return

        self.meeting_id = self.scope["url_route"]["kwargs"].get("meeting_id")
        self.meeting = await self.get_meeting(self.meeting_id)

        if not self.meeting or self.meeting.is_completed or not self.meeting.is_active:
            await self.accept()
            await self.send_json(
                {
                    "type": "error",
                    "code": 404,
                    "message": "Ushbu yig'ilish allaqachon tugagan yoki mavjud emas.",
                }
            )
            await self.close(code=4004)
            return

        is_allowed = await self.check_user_permission(self.user, self.meeting)
        if not is_allowed:
            await self.accept()
            await self.send_json(
                {
                    "type": "error",
                    "code": 403,
                    "message": "Siz ushbu yig'ilish qatnashchisi emassiz.",
                }
            )
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

        ws_cache_key = self.scope.get("ws_cache_key")
        if ws_cache_key:
            cache.delete(ws_cache_key)

        organizer_joined = await self.is_organizer_joined(self.meeting)
        is_approved = await self.get_approval_status(self.meeting.id, self.user.id)

        token = None
        if (
            is_host
            or is_approved
            or (not self.meeting.requires_approval and organizer_joined)
        ):
            token = await self.get_livekit_token(self.user.id, self.meeting)

        raised_hands = await self.get_raised_hands(self.meeting.id)

        await self.send_json(
            {
                "type": "meeting_state",
                "meeting_id": self.meeting.id,
                "title": self.meeting.title,
                "requires_approval": self.meeting.requires_approval,
                "organizer_joined": organizer_joined,
                "is_host": is_host,
                "is_approved": bool(is_approved or is_host),
                "token": token,
                "server_url": settings.LIVEKIT_URL if token else None,
                "room_name": self.meeting.uid if token else None,
                "raised_hands": raised_hands,
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, "room_group"):
            await self.channel_layer.group_discard(self.room_group, self.channel_name)
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, "hosts_group"):
            await self.channel_layer.group_discard(self.hosts_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action")

        if action == "ask_to_join":
            await self.handle_ask_to_join(content)
        elif action == "admit":
            await self.handle_admit(content)
        elif action == "get_token":
            await self.handle_get_token(content)
        elif action == "hand_raise":
            await self.handle_hand_raise(content)
        elif action in ["send_reaction", "reaction"]:
            await self.handle_send_reaction(content)
        elif action == "moderate_track":
            await self.handle_moderate_track(content)
        elif action == "request_track_unmute":
            await self.handle_request_track_unmute(content)
        elif action == "respond_track_unmute_request":
            await self.handle_respond_track_unmute_request(content)
        else:
            await self.send_json(
                {
                    "type": "error",
                    "code": "unknown_action",
                    "message": f"Noma'lum amal: '{action}'",
                }
            )

    async def handle_get_token(self, content=None):
        fresh_meeting = await self.get_meeting(self.meeting_id)
        if fresh_meeting:
            self.meeting = fresh_meeting
        is_host = await self.is_host_or_admin(self.user, self.meeting)
        if not is_host:
            organizer_joined = await self.is_organizer_joined(self.meeting)
            if not organizer_joined:
                await self.send_json(
                    {
                        "type": "token_response",
                        "status": "waiting",
                        "message": "Tashkilotchi yig'ilishga kirmaguncha kuting.",
                    }
                )
                return

            if self.meeting.requires_approval:
                is_approved = await self.get_approval_status(
                    self.meeting.id, self.user.id
                )
                if not is_approved:
                    await self.send_json(
                        {
                            "type": "token_response",
                            "status": "waiting_approval",
                            "message": "Tashkilotchi tasdiqlashini kuting.",
                        }
                    )
                    return

        device_id = None
        device_name = None
        if content and isinstance(content, dict):
            device_id = content.get("device_id") or content.get("session_id")
            device_name = content.get("device_name")

        token = await self.get_livekit_token(
            self.user.id, self.meeting, device_id=device_id, device_name=device_name
        )
        await self.send_json(
            {
                "type": "token_response",
                "status": "joined",
                "server_url": settings.LIVEKIT_URL,
                "room_name": self.meeting.uid,
                "token": token,
            }
        )

    async def handle_ask_to_join(self, content):
        avatar_url = None
        if hasattr(self.user, "avatar") and self.user.avatar:
            try:
                avatar_url = self.user.avatar.url
            except Exception:
                avatar_url = None

        knock_data = {
            "type": "knock_request",
            "meeting_id": self.meeting.id,
            "user_id": self.user.id,
            "username": self.user.username,
            "full_name": self.user.get_full_name() or self.user.username,
            "avatar": avatar_url,
        }

        hosts_group = f"meeting_{self.meeting_id}_hosts"
        await self.channel_layer.group_send(
            hosts_group, {"type": "knock_request", "data": knock_data}
        )

    async def handle_admit(self, content):
        is_host = await self.is_host_or_admin(self.user, self.meeting)
        if not is_host:
            await self.send_json(
                {
                    "type": "error",
                    "code": "not_allowed",
                    "message": "Faqat mezbon ruxsat bera oladi.",
                }
            )
            return

        target_user_id = content.get("user_id")
        if not target_user_id:
            await self.send_json(
                {
                    "type": "error",
                    "code": "invalid_request",
                    "message": "user_id ko'rsatilishi shart.",
                }
            )
            return

        is_participant = await self.check_user_id_permission(
            target_user_id, self.meeting
        )
        if not is_participant:
            await self.send_json(
                {
                    "type": "error",
                    "code": "participant_not_found",
                    "message": "Foydalanuvchi ushbu yig'ilish qatnashchisi emas.",
                }
            )
            return

        decision = content.get("decision", "reject")
        target_group = f"meeting_{self.meeting_id}_user_{target_user_id}"

        if decision == "approve":
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
                        "token": token,
                    },
                },
            )
        else:
            await self.channel_layer.group_send(
                target_group,
                {
                    "type": "knock_response",
                    "data": {
                        "type": "knock_response",
                        "status": "rejected",
                        "message": "Mezbon yig'ilishga kirishingizni rad etdi.",
                    },
                },
            )

    async def handle_hand_raise(self, content):
        raised = bool(content.get("raised", True))
        await self.update_hand_raise_cache(self.meeting.id, self.user, raised)

        await self.channel_layer.group_send(
            self.room_group,
            {
                "type": "hand_raise_updated",
                "data": {
                    "type": "hand_raise_updated",
                    "user_id": self.user.id,
                    "username": self.user.username,
                    "full_name": self.user.get_full_name() or self.user.username,
                    "raised": raised,
                    "raised_at": timezone.now().isoformat() if raised else None,
                },
            },
        )

    async def handle_send_reaction(self, content):
        reaction = content.get("reaction") or content.get("emoji")
        if not reaction or not isinstance(reaction, str):
            return

        reaction = reaction.strip()[:16]

        await self.channel_layer.group_send(
            self.room_group,
            {
                "type": "reaction_received",
                "data": {
                    "type": "reaction_received",
                    "user_id": self.user.id,
                    "username": self.user.username,
                    "full_name": self.user.get_full_name() or self.user.username,
                    "reaction": reaction,
                    "sent_at": timezone.now().isoformat(),
                },
            },
        )

    async def handle_moderate_track(self, content):
        is_host = await self.is_host_or_admin(self.user, self.meeting)
        if not is_host:
            await self.send_json(
                {
                    "type": "moderation_error",
                    "code": "not_allowed",
                    "message": "Faqat mezbon qatnashchilarni boshqara oladi.",
                }
            )
            return

        target_identity = content.get("target_identity")
        track_source = content.get("track_source", "microphone")
        operation = content.get("operation", "mute")

        if not target_identity:
            await self.send_json(
                {
                    "type": "moderation_error",
                    "code": "invalid_request",
                    "message": "target_identity ko'rsatilishi shart.",
                }
            )
            return

        if operation == "mute":
            success, err = await LiveKitService.async_mute_track(
                self.meeting.uid, target_identity, track_source=track_source, muted=True
            )
            if not success:
                await self.send_json(
                    {
                        "type": "moderation_error",
                        "code": err or "livekit_error",
                        "message": "Qatnashchi trackini o'chirib bo'lmadi.",
                    }
                )
                return

            raw_target_uid = target_identity.split("_")[0] if target_identity else None
            parsed_uid = int(raw_target_uid) if raw_target_uid and raw_target_uid.isdigit() else None

            await self.channel_layer.group_send(
                self.room_group,
                {
                    "type": "track_moderation_changed",
                    "data": {
                        "type": "track_moderation_changed",
                        "meeting_id": self.meeting.id,
                        "target_identity": target_identity,
                        "user_id": parsed_uid,
                        "track_source": track_source,
                        "muted": True,
                        "actor_user_id": self.user.id,
                        "changed_at": timezone.now().isoformat(),
                    },
                },
            )

    async def handle_request_track_unmute(self, content):
        is_host = await self.is_host_or_admin(self.user, self.meeting)
        if not is_host:
            await self.send_json(
                {
                    "type": "error",
                    "code": "not_allowed",
                    "message": "Faqat mezbon unmute so'rovi yubora oladi.",
                }
            )
            return

        target_identity = content.get("target_identity")
        target_user_id = content.get("target_user_id")

        if not target_user_id and target_identity:
            raw_uid = target_identity.split("_")[0]
            if raw_uid.isdigit():
                target_user_id = int(raw_uid)

        if not target_user_id:
            await self.send_json(
                {
                    "type": "error",
                    "code": "invalid_request",
                    "message": "target_user_id aniqlanmadi.",
                }
            )
            return

        track_source = content.get("track_source", "microphone")
        request_id = content.get("request_id") or str(uuid.uuid4())

        await self.channel_layer.group_send(
            f"meeting_{self.meeting_id}_user_{target_user_id}",
            {
                "type": "track_unmute_requested",
                "data": {
                    "type": "track_unmute_requested",
                    "request_id": request_id,
                    "from_user_id": self.user.id,
                    "from_name": self.user.get_full_name() or self.user.username,
                    "target_identity": target_identity,
                    "track_source": track_source,
                },
            },
        )

    async def handle_respond_track_unmute_request(self, content):
        request_id = content.get("request_id")
        decision = content.get("decision", "accept")
        track_source = content.get("track_source", "microphone")
        target_identity = content.get("target_identity")

        hosts_group = f"meeting_{self.meeting_id}_hosts"
        await self.channel_layer.group_send(
            hosts_group,
            {
                "type": "track_unmute_request_result",
                "data": {
                    "type": "track_unmute_request_result",
                    "request_id": request_id,
                    "user_id": self.user.id,
                    "decision": decision,
                    "target_identity": target_identity,
                    "track_source": track_source,
                },
            },
        )

    async def knock_request(self, event):
        await self.send_json(event["data"])

    async def knock_response(self, event):
        await self.send_json(event["data"])

    async def hand_raise_updated(self, event):
        await self.send_json(event["data"])

    async def reaction_received(self, event):
        await self.send_json(event["data"])

    async def track_moderation_changed(self, event):
        await self.send_json(event["data"])

    async def track_unmute_requested(self, event):
        await self.send_json(event["data"])

    async def track_unmute_request_result(self, event):
        await self.send_json(event["data"])

    async def meeting_broadcast(self, event):
        data = event.get("data", {})
        if data.get("type") == "organizer_joined":
            if (
                not self.meeting.requires_approval
                and self.user.id != self.meeting.organizer_id
            ):
                token = await self.get_livekit_token(self.user.id, self.meeting)
                await self.send_json(
                    {
                        "type": "token_response",
                        "status": "joined",
                        "server_url": settings.LIVEKIT_URL,
                        "room_name": self.meeting.uid,
                        "token": token,
                    }
                )
        await self.send_json(data)

    @database_sync_to_async
    def get_meeting(self, meeting_id):
        return (
            Meeting.objects.filter(id=meeting_id)
            .select_related("project", "organizer")
            .first()
        )

    @database_sync_to_async
    def check_user_permission(self, user, meeting):
        if meeting.organizer_id == user.id:
            return True
        return meeting.participants.filter(id=user.id).exists()

    @database_sync_to_async
    def check_user_id_permission(self, user_id, meeting):
        if meeting.organizer_id == user_id:
            return True
        return meeting.participants.filter(id=user_id).exists()

    @database_sync_to_async
    def is_host_or_admin(self, user, meeting):
        if meeting.organizer_id == user.id:
            return True
        is_participant = meeting.participants.filter(id=user.id).exists()
        if is_participant and (
            user.is_superuser
            or user.has_role(Role.ADMIN)
            or (meeting.project and meeting.project.manager_id == user.id)
        ):
            return True
        return False

    @database_sync_to_async
    def is_organizer_joined(self, meeting):
        from apps.projects.models import MeetingAttendance

        return MeetingAttendance.objects.filter(
            meeting=meeting, user_id=meeting.organizer_id, is_attended=True
        ).exists()

    @database_sync_to_async
    def get_approval_status(self, meeting_id, user_id):
        return bool(cache.get(f"meeting_{meeting_id}_approved_{user_id}"))

    @database_sync_to_async
    def set_approval_cache(self, meeting_id, user_id):
        cache.set(f"meeting_{meeting_id}_approved_{user_id}", True, timeout=86400)

    @database_sync_to_async
    def get_livekit_token(self, user_id, meeting, device_id=None, device_name=None):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        target_user = User.objects.get(id=user_id)
        return LiveKitService.generate_token(
            target_user, meeting, device_id=device_id, device_name=device_name
        )

    @database_sync_to_async
    def get_raised_hands(self, meeting_id):
        cache_key = f"meeting_{meeting_id}_raised_hands"
        hands_dict = cache.get(cache_key) or {}
        return list(hands_dict.values())

    @database_sync_to_async
    def update_hand_raise_cache(self, meeting_id, user, raised):
        cache_key = f"meeting_{meeting_id}_raised_hands"
        hands_dict = cache.get(cache_key) or {}
        user_key = str(user.id)
        if raised:
            hands_dict[user_key] = {
                "user_id": user.id,
                "username": user.username,
                "full_name": user.get_full_name() or user.username,
                "raised_at": timezone.now().isoformat(),
            }
        else:
            hands_dict.pop(user_key, None)
        cache.set(cache_key, hands_dict, timeout=86400)
        return list(hands_dict.values())
