import json
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied
from livekit import api

from .models import TaskStatus, MeetingAttendance, Meeting, Task
from apps.notifications.models import Notification, NotificationType
from apps.users.models import Role


class TaskService:
    STATUS_ORDER = {
        TaskStatus.TODO: 1,
        TaskStatus.IN_PROGRESS: 2,
        TaskStatus.DONE: 3,
        TaskStatus.PRODUCTION: 4,
        TaskStatus.CHECKED: 5,
        TaskStatus.REJECTED: 5,
    }

    @classmethod
    @transaction.atomic
    def create_task(cls, user, validated_data):
        task = Task.objects.create(created_by=user, **validated_data)

        if task.assignee and task.assignee != user:
            deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M")
            cls._send_task_notification(
                task.assignee,
                task,
                "Yangi vazifa biriktirildi",
                f"Sizga {task.title} nomli yangi vazifa topshirildi. Muddati: {deadline_str}",
            )

        manager = task.project.manager
        if manager and manager != user:
            cls._send_task_notification(
                manager,
                task,
                "Yangi vazifa yaratildi",
                f"Loyihangizda yangi vazifa yaratildi: {task.title}. Yaratuvchi: {user.username}",
            )

        return task

    @classmethod
    @transaction.atomic
    def change_status(cls, task, user, new_status, rejection_reason=None):
        current_status = task.status
        if not new_status or current_status == new_status:
            return task

        now = timezone.now()
        updated_task = None

        is_admin = user.is_superuser or user.has_role(Role.ADMIN)

        if is_admin:
            updated_task = cls._handle_admin_full_control(
                task, user, new_status, rejection_reason, now
            )
        elif new_status in [TaskStatus.CHECKED, TaskStatus.REJECTED]:
            if task.project.manager == user:
                updated_task = cls._handle_manager_logic(
                    task, user, new_status, rejection_reason, now
                )
            else:
                is_tester = task.project.testers.filter(id=user.id).exists()
                if is_tester:
                    if task.assignee_id == user.id:
                        raise PermissionDenied(
                            "O'zingiz topshirgan vazifani o'zingiz tekshira olmaysiz!"
                        )
                    updated_task = cls._handle_tester_logic(
                        task, user, new_status, rejection_reason, now
                    )
                else:
                    raise PermissionDenied(
                        "Sizda ushbu vazifaning statusini o'zgartirish huquqi yo'q."
                    )

        else:
            if task.assignee == user:
                updated_task = cls._handle_assignee_logic(task, user, new_status, now)
            elif (
                task.assignee is None
                and task.project.employees.filter(id=user.id).exists()
            ):
                updated_task = cls._handle_claim_logic(task, user, new_status, now)
            else:
                raise PermissionDenied(
                    "Sizda ushbu vazifaning statusini o'zgartirish huquqi yo'q."
                )

        if updated_task:
            recipients = set()

            if updated_task.created_by:
                recipients.add(updated_task.created_by)

            if updated_task.project:
                if updated_task.project.created_by:
                    recipients.add(updated_task.project.created_by)
                if updated_task.project.manager:
                    recipients.add(updated_task.project.manager)

            if updated_task.assignee:
                recipients.add(updated_task.assignee)

            recipients = [r for r in recipients if r != user]

            if recipients:
                status_display = updated_task.get_status_display()
                for recipient in recipients:
                    cls._send_task_notification(
                        recipient,
                        updated_task,
                        "Vazifa holati o'zgardi",
                        f"'{updated_task.title}' vazifasining holati '{status_display}' ga o'zgartirildi.",
                        extra_data={
                            "action": "task_status_changed",
                            "old_status": current_status,
                            "new_status": updated_task.status,
                        },
                    )

        return updated_task

    @classmethod
    def _handle_admin_full_control(cls, task, user, new_status, rejection_reason, now):
        task._current_user = user

        if new_status == TaskStatus.REJECTED:
            if rejection_reason and rejection_reason.strip():
                return cls._apply_rejection(
                    task, rejection_reason, now, "Vazifa rad etildi"
                )
            task.status = TaskStatus.REJECTED
            task.started_at = None
            task.save()
            return task

        cls._update_task_time_and_status(task, new_status, now)
        if new_status == TaskStatus.CHECKED:
            cls._send_task_notification(
                task.assignee,
                task,
                "Vazifa tasdiqlandi",
                "Siz topshirgan vazifa tasdiqlandi.",
            )
        return task

    @classmethod
    def _handle_manager_logic(cls, task, user, new_status, rejection_reason, now):
        if new_status not in [TaskStatus.CHECKED, TaskStatus.REJECTED]:
            raise PermissionDenied(
                "Menejer faqat vazifani tekshirish yoki rad etish huquqiga ega."
            )

        if new_status == TaskStatus.REJECTED:
            return cls._apply_rejection(
                task, rejection_reason, now, "Vazifa rad etildi"
            )

        if cls.STATUS_ORDER.get(new_status, 0) < cls.STATUS_ORDER.get(task.status, 0):
            raise PermissionDenied("Statusni orqaga qaytara olmaysiz.")

        cls._update_task_time_and_status(task, new_status, now)
        if new_status == TaskStatus.CHECKED:
            cls._send_task_notification(
                task.assignee,
                task,
                "Vazifa tasdiqlandi",
                "Siz topshirgan vazifa tasdiqlandi.",
            )
        return task

    @classmethod
    def _handle_tester_logic(cls, task, user, new_status, rejection_reason, now):
        if task.status != TaskStatus.PRODUCTION:
            raise PermissionDenied(
                "Faqat ishga tushurilgan vazifalarni tekshirish mumkin."
            )

        if new_status == TaskStatus.REJECTED:
            return cls._apply_rejection(
                task, rejection_reason, now, "Topshirilgan vazifa rad etildi"
            )

        if new_status == TaskStatus.CHECKED:
            task.status = TaskStatus.CHECKED
            task.save()
            cls._send_task_notification(
                task.assignee,
                task,
                "Topshirilgan vazifa tasdiqlandi",
                "Siz topshirgan vazifa tasdiqlandi.",
            )
            return task

    @classmethod
    def _handle_assignee_logic(cls, task, user, new_status, now):
        transitions = {
            TaskStatus.TODO: [TaskStatus.IN_PROGRESS],
            TaskStatus.IN_PROGRESS: [TaskStatus.DONE],
            TaskStatus.OVERDUE: [TaskStatus.DONE, TaskStatus.IN_PROGRESS],
            TaskStatus.DONE: [TaskStatus.PRODUCTION],
            TaskStatus.REJECTED: [TaskStatus.IN_PROGRESS],
        }
        if new_status not in transitions.get(task.status, []):
            raise PermissionDenied(
                "Bu bosqichga o'tishga ruxsat yo'q yoki status orqaga qaytaryapsiz."
            )

        cls._update_task_time_and_status(task, new_status, now)
        return task

    @classmethod
    def _handle_claim_logic(cls, task, user, new_status, now):
        if not user.has_role(Role.EMPLOYEE):
            raise PermissionDenied("Vazifani faqat xodimlar o'zlashtirishi mumkin.")

        if new_status != TaskStatus.IN_PROGRESS:
            raise PermissionDenied("Vazifani olish uchun uni jarayonga o'tkazing.")

        if task.position_id and user.position_id != task.position_id:
            raise PermissionDenied(
                f"Bu vazifa faqat {task.position.name} lavozimi uchun."
            )

        task.assignee = user
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = now
        task.save()
        return task

    @classmethod
    def _update_task_time_and_status(cls, task, new_status, now):
        if (
            new_status in [TaskStatus.DONE, TaskStatus.PRODUCTION, TaskStatus.CHECKED]
            and task.started_at
        ):
            diff_seconds = (now - task.started_at).total_seconds()

            if diff_seconds >= 60:
                elapsed_minutes = int(diff_seconds / 60)
                task.actual_minutes += elapsed_minutes

            task.started_at = None

        task.status = new_status

        if new_status == TaskStatus.IN_PROGRESS:
            if not task.started_at:
                task.started_at = now
        else:
            task.started_at = None

        task.save()

    @classmethod
    def _apply_rejection(cls, task, reason, now, title):
        if not reason or not reason.strip():
            raise ValidationError(
                {"rejection_reason": "Rad etish sababini yozish shart!"}
            )

        if task.status in [TaskStatus.DONE, TaskStatus.PRODUCTION, TaskStatus.CHECKED]:
            task.reopened_count += 1

        timestamp = timezone.localtime(now).strftime("%d.%m.%Y %H:%M")
        task.rejection_reason = (
            f"{task.rejection_reason}\n\n" if task.rejection_reason else ""
        ) + f"[{timestamp}] {reason}"

        task.status = TaskStatus.IN_PROGRESS
        task.started_at = now
        task.save()

        cls._send_task_notification(task.assignee, task, title, f"Sabab: {reason}")
        return task

    @staticmethod
    def _send_task_notification(user, task, title, message, extra_data=None):
        if user:
            payload = {
                "task_id": task.id,
                "action": "open_task",
                "project_id": task.project_id,
            }
            if extra_data:
                payload.update(extra_data)

            Notification.objects.create(
                user=user,
                title=title,
                message=message,
                type=NotificationType.TASK,
                extra_data=payload,
            )


class MeetingService:
    @staticmethod
    def _send_meeting_notifications(
        meeting,
        members,
        organizer_id,
        title="Yangi yig'ilish belgilandi",
        msg_template=None,
    ):
        notifications_to_bulk = []
        broadcast_data = []
        start_time_str = meeting.start_time.strftime("%d.%m.%Y %H:%M")

        if msg_template is None:
            msg_template = f"{meeting.title} yig'ilish tayinlandi. Vaqti: {start_time_str}. Davomiyligi: {meeting.duration_minutes} daqiqa."

        for member in members:
            if member.id != organizer_id:
                notifications_to_bulk.append(
                    Notification(
                        user=member,
                        title=title,
                        message=msg_template,
                        type=NotificationType.MEETING,
                    )
                )

                broadcast_data.append(
                    {
                        "user_id": member.id,
                        "title": title,
                        "message": msg_template,
                        "type": "meeting",
                        "extra_data": {
                            "meeting_id": meeting.id,
                            "action": "open_meeting",
                            "project_id": meeting.project_id,
                        },
                    }
                )

        if notifications_to_bulk:
            Notification.objects.bulk_create(notifications_to_bulk)

            from apps.notifications.tasks import mass_notification_sender

            transaction.on_commit(
                lambda: mass_notification_sender.delay(broadcast_data)
            )

    @classmethod
    @transaction.atomic
    def handle_participants(cls, meeting, participants, organizer_id):
        if participants is None:
            return

        current_attendees = MeetingAttendance.objects.filter(
            meeting=meeting
        ).select_related("user")
        current_attendee_ids = {a.user_id for a in current_attendees}
        new_participant_ids = {p.id for p in participants}

        if organizer_id not in new_participant_ids:
            new_participant_ids.add(organizer_id)

        to_remove_attendees = [
            a for a in current_attendees if a.user_id not in new_participant_ids
        ]
        if to_remove_attendees:
            removed_users = [a.user for a in to_remove_attendees]
            MeetingAttendance.objects.filter(
                id__in=[a.id for a in to_remove_attendees]
            ).delete()
            cls._send_meeting_notifications(
                meeting,
                removed_users,
                organizer_id,
                title="Yig'ilishdan chiqarildingiz",
                msg_template=f"Siz '{meeting.title}' yig'ilishi qatnashchilari ro'yxatidan chiqarildingiz.",
            )

        to_add_ids = new_participant_ids - current_attendee_ids

        if to_add_ids:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            to_add_users = User.objects.filter(id__in=to_add_ids)

            attendances = [
                MeetingAttendance(user=user, meeting=meeting) for user in to_add_users
            ]
            MeetingAttendance.objects.bulk_create(attendances)
            cls._send_meeting_notifications(meeting, to_add_users, organizer_id)

    @classmethod
    @transaction.atomic
    def create_meeting(cls, organizer, validated_data):
        participants = validated_data.pop("participants", [])
        meeting = Meeting.objects.create(organizer=organizer, **validated_data)
        cls.handle_participants(meeting, participants, organizer.id)
        return meeting

    @classmethod
    @transaction.atomic
    def close_meeting(cls, meeting):
        if meeting.is_completed:
            raise ValidationError({"detail": "Bu yig'ilish allaqachon tugagan."})

        meeting.is_completed = True
        meeting.completed_at = timezone.now()
        meeting.save()

        active_attendances = MeetingAttendance.objects.filter(
            meeting=meeting,
            is_attended=True,
            joined_at__isnull=False,
            left_at__isnull=True,
        )
        for att in active_attendances:
            att.left_at = meeting.completed_at
            duration_secs = (meeting.completed_at - att.joined_at).total_seconds()
            att.duration_minutes = max(
                att.duration_minutes or 0, int(duration_secs // 60)
            )
            att.save(update_fields=["left_at", "duration_minutes", "updated_at"])

        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"meeting_{meeting.id}",
                {
                    "type": "meeting_broadcast",
                    "data": {
                        "type": "meeting_ended",
                        "meeting_id": meeting.id,
                        "message": "Yig'ilish tugatildi.",
                    },
                },
            )

        LiveKitService.delete_room(meeting.uid)

        absent_attendances = MeetingAttendance.objects.filter(
            meeting=meeting, is_attended=False
        ).select_related("user")

        notifications_to_bulk = []
        broadcast_data = []

        for attendance in absent_attendances:
            msg = f"Siz {meeting.title} yig'ilishda qatnashmadingiz. Sababini ko'rsatishingiz so'raladi."

            notifications_to_bulk.append(
                Notification(
                    user_id=attendance.user.id,
                    title="Yig'ilishda ishtirok etmadingiz.",
                    message=msg,
                    type=NotificationType.MEETING,
                    extra_data={
                        "meeting_id": meeting.id,
                        "action": "open_meeting",
                        "project_id": meeting.project_id,
                    },
                )
            )

            broadcast_data.append(
                {
                    "user_id": attendance.user.id,
                    "title": "Yig'ilishda ishtirok etmadingiz.",
                    "message": msg,
                    "type": NotificationType.MEETING,
                    "extra_data": {
                        "meeting_id": meeting.id,
                        "action": "open_meeting",
                        "project_id": meeting.project_id,
                    },
                }
            )

        if notifications_to_bulk:
            Notification.objects.bulk_create(notifications_to_bulk)

            from apps.notifications.tasks import mass_notification_sender

            transaction.on_commit(
                lambda: mass_notification_sender.delay(broadcast_data)
            )

        return meeting

    @classmethod
    def notify_time_change(cls, meeting):
        participants = meeting.participants.all()
        start_time_str = meeting.start_time.strftime("%d.%m.%Y %H:%M")

        notifications_to_bulk = []
        broadcast_data = []

        msg = f"'{meeting.title}' yig'ilishi vaqti o'zgardi. Yangi vaqt: {start_time_str}. Davomiyligi: {meeting.duration_minutes} daqiqa."

        for member in participants:
            if member.id != meeting.organizer_id:
                notifications_to_bulk.append(
                    Notification(
                        user=member,
                        title="Yig'ilish vaqti o'zgardi",
                        message=msg,
                        type=NotificationType.MEETING,
                    )
                )

                broadcast_data.append(
                    {
                        "user_id": member.id,
                        "title": "Yig'ilish vaqti o'zgardi",
                        "message": msg,
                        "type": "meeting",
                        "extra_data": {
                            "meeting_id": meeting.id,
                            "action": "open_meeting",
                            "project_id": meeting.project_id,
                        },
                    }
                )

        if notifications_to_bulk:
            Notification.objects.bulk_create(notifications_to_bulk)
            from apps.notifications.tasks import mass_notification_sender

            transaction.on_commit(
                lambda: mass_notification_sender.delay(broadcast_data)
            )

    @classmethod
    def notify_meeting_started(cls, meeting):
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from apps.notifications.models import Notification, NotificationType
        from apps.notifications.tasks import mass_notification_sender

        attended_user_ids = set(
            MeetingAttendance.objects.filter(
                meeting=meeting, is_attended=True, left_at__isnull=True
            ).values_list("user_id", flat=True)
        )
        attended_user_ids.add(meeting.organizer_id)

        unattended_participants = meeting.participants.exclude(id__in=attended_user_ids)

        notifications_to_create = []
        broadcast_data = []
        msg = f"'{meeting.title}' yig'ilishi boshlandi. Yig'ilishga kirishingiz mumkin."
        title = "Yig'ilish boshlandi"

        for participant in unattended_participants:
            extra = {
                "meeting_id": meeting.id,
                "room_name": meeting.uid,
                "action": "join_meeting",
            }
            notifications_to_create.append(
                Notification(
                    user=participant,
                    title=title,
                    message=msg,
                    type=NotificationType.MEETING,
                    extra_data=extra,
                )
            )
            broadcast_data.append(
                {
                    "user_id": participant.id,
                    "title": title,
                    "message": msg,
                    "type": "meeting",
                    "extra_data": extra,
                }
            )

        if notifications_to_create:
            Notification.objects.bulk_create(notifications_to_create)
            transaction.on_commit(
                lambda: mass_notification_sender.delay(broadcast_data)
            )

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"meeting_{meeting.id}",
                {
                    "type": "meeting_broadcast",
                    "data": {
                        "type": "organizer_joined",
                        "meeting_id": meeting.id,
                        "message": "Tashkilotchi yig'ilishga kirdi.",
                    },
                },
            )

    @classmethod
    def notify_participant_late(cls, meeting, user, late_minutes):
        from apps.notifications.tasks import mass_notification_sender

        msg = f"Siz '{meeting.title}' yig'ilishiga {late_minutes} daqiqa kechikib kirdingiz. 24 soat ichida kechikish sababini ko'rsatishingiz so'raladi."
        title = "Yig'ilishga kechikib kirdingiz"

        Notification.objects.create(
            user=user,
            title=title,
            message=msg,
            type=NotificationType.MEETING,
            extra_data={
                "meeting_id": meeting.id,
                "action": "open_meeting",
                "late_minutes": late_minutes,
            },
        )

        broadcast_data = [
            {
                "user_id": user.id,
                "title": title,
                "message": msg,
                "type": "meeting",
                "extra_data": {
                    "meeting_id": meeting.id,
                    "action": "open_meeting",
                    "late_minutes": late_minutes,
                },
            }
        ]
        transaction.on_commit(lambda: mass_notification_sender.delay(broadcast_data))


class LiveKitService:
    @staticmethod
    def generate_token(user, meeting, device_id=None, device_name=None):
        api_key = settings.LIVEKIT_API_KEY
        api_secret = settings.LIVEKIT_API_SECRET

        is_organizer = meeting.organizer_id == user.id
        is_participant = meeting.participants.filter(id=user.id).exists()
        grants = api.VideoGrants(
            room_join=True,
            room=meeting.uid,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
            room_create=False,
            room_admin=False,
            room_record=False,
        )

        unique_suffix = str(device_id).strip() if device_id else uuid.uuid4().hex[:6]
        participant_identity = f"{user.id}_{unique_suffix}"

        base_name = user.get_full_name() or user.username
        clean_device_name = str(device_name).strip() if device_name else None
        participant_name = (
            f"{base_name} ({clean_device_name})" if clean_device_name else base_name
        )

        metadata = {
            "user_id": user.id,
            "username": user.username,
            "full_name": base_name,
            "device_id": unique_suffix,
            "is_organizer": is_organizer,
        }
        if clean_device_name:
            metadata["device_name"] = clean_device_name

        token = (
            api.AccessToken(api_key, api_secret)
            .with_identity(participant_identity)
            .with_name(participant_name)
            .with_metadata(json.dumps(metadata))
            .with_grants(grants)
            .with_ttl(timedelta(hours=12))
        )

        return token.to_jwt()

    @classmethod
    async def async_mute_track(
        cls, room_name, participant_identity, track_source="microphone", muted=True
    ):
        http_url = getattr(settings, "LIVEKIT_INTERNAL_URL", "http://127.0.0.1:7880")
        api_key = settings.LIVEKIT_API_KEY
        api_secret = settings.LIVEKIT_API_SECRET

        try:
            async with api.LiveKitAPI(http_url, api_key, api_secret) as lk:
                participant = await lk.room.get_participant(
                    api.RoomParticipantIdentity(
                        room=room_name, identity=participant_identity
                    )
                )
                target_source = (
                    api.TrackSource.MICROPHONE
                    if track_source == "microphone"
                    else api.TrackSource.CAMERA
                )
                track_sid = None
                for track in participant.tracks:
                    if track.source == target_source:
                        track_sid = track.sid
                        break
                    if not track_sid:
                        if (
                            track_source == "microphone"
                            and track.type == api.TrackType.AUDIO
                        ):
                            track_sid = track.sid
                        elif (
                            track_source == "camera"
                            and track.type == api.TrackType.VIDEO
                            and track.source != api.TrackSource.SCREEN_SHARE
                        ):
                            track_sid = track.sid

                if not track_sid:
                    return False, "track_not_published"

                await lk.room.mute_published_track(
                    api.MuteRoomTrackRequest(
                        room=room_name,
                        identity=participant_identity,
                        track_sid=track_sid,
                        muted=muted,
                    )
                )
                return True, None
        except Exception as e:
            return False, str(e)

    @classmethod
    def mute_track(
        cls, room_name, participant_identity, track_source="microphone", muted=True
    ):
        from asgiref.sync import async_to_sync

        return async_to_sync(cls.async_mute_track)(
            room_name, participant_identity, track_source, muted
        )

    @classmethod
    def delete_room(cls, room_name):
        from asgiref.sync import async_to_sync

        http_url = getattr(settings, "LIVEKIT_INTERNAL_URL", "http://127.0.0.1:7880")

        async def _delete():
            try:
                async with api.LiveKitAPI(
                    http_url, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET
                ) as lk:
                    await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
            except Exception:
                pass

        try:
            async_to_sync(_delete)()
        except Exception:
            pass

    @staticmethod
    def handle_webhook(body_str, auth_header):
        api_key = settings.LIVEKIT_API_KEY
        api_secret = settings.LIVEKIT_API_SECRET

        verifier = api.TokenVerifier(api_key, api_secret)
        receiver = api.WebhookReceiver(verifier)
        event = receiver.receive(body_str, auth_header)

        event_type = event.event
        room = event.room
        participant = event.participant

        if not room or not room.name:
            return

        meeting = Meeting.objects.filter(uid=room.name, is_active=True).first()
        if not meeting:
            return

        if event_type == "participant_joined" and participant:
            raw_identity = participant.identity or ""
            raw_user_id = raw_identity.split("_")[0] if raw_identity else None
            if not raw_user_id and participant.metadata:
                try:
                    raw_user_id = json.loads(participant.metadata).get("user_id")
                except Exception:
                    raw_user_id = None

            try:
                user_id = int(raw_user_id)
            except (ValueError, TypeError):
                user_id = None

            if not user_id:
                return

            devices_cache_key = f"meeting_{meeting.id}_user_{user_id}_active_devices"
            active_devices = cache.get(devices_cache_key) or set()
            active_devices.add(raw_identity)
            cache.set(devices_cache_key, active_devices, timeout=86400)

            att = MeetingAttendance.objects.filter(
                meeting=meeting, user_id=user_id
            ).first()
            was_attended = att.is_attended if att else False
            now = timezone.now()
            is_organizer = str(meeting.organizer_id) == str(user_id)

            calc_late_minutes = 0
            if not is_organizer:
                org_att = MeetingAttendance.objects.filter(
                    meeting=meeting, user_id=meeting.organizer_id
                ).first()
                org_joined_at = org_att.joined_at if org_att else None
                base_start_time = meeting.start_time
                if org_joined_at and meeting.start_time:
                    base_start_time = max(meeting.start_time, org_joined_at)
                elif org_joined_at:
                    base_start_time = org_joined_at

                if att and att.created_at:
                    if base_start_time:
                        base_start_time = max(base_start_time, att.created_at)
                    else:
                        base_start_time = att.created_at
                elif not att:
                    base_start_time = now

                if base_start_time and now > base_start_time:
                    delay_minutes = int((now - base_start_time).total_seconds() // 60)
                    if delay_minutes > 5:
                        calc_late_minutes = delay_minutes

            if att:
                att.is_attended = True
                if not att.joined_at:
                    att.joined_at = now
                    att.late_minutes = calc_late_minutes
                att.save(
                    update_fields=[
                        "is_attended",
                        "joined_at",
                        "late_minutes",
                        "updated_at",
                    ]
                )
            else:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                target_user = User.objects.filter(id=user_id).first()
                if target_user:
                    att = MeetingAttendance.objects.create(
                        meeting=meeting,
                        user=target_user,
                        is_attended=True,
                        joined_at=now,
                        late_minutes=calc_late_minutes,
                    )

            if att and att.late_minutes > 5 and not was_attended and not is_organizer:
                MeetingService.notify_participant_late(
                    meeting, att.user, att.late_minutes
                )

            if is_organizer and not was_attended:
                MeetingService.notify_meeting_started(meeting)

        elif event_type == "participant_left" and participant:
            raw_identity = participant.identity or ""
            raw_user_id = raw_identity.split("_")[0] if raw_identity else None
            if not raw_user_id and participant.metadata:
                try:
                    raw_user_id = json.loads(participant.metadata).get("user_id")
                except Exception:
                    raw_user_id = None

            try:
                user_id = int(raw_user_id)
            except (ValueError, TypeError):
                user_id = None

            if not user_id:
                return

            devices_cache_key = f"meeting_{meeting.id}_user_{user_id}_active_devices"
            active_devices = cache.get(devices_cache_key) or set()
            active_devices.discard(raw_identity)
            cache.set(devices_cache_key, active_devices, timeout=86400)

            if len(active_devices) == 0:
                att = MeetingAttendance.objects.filter(
                    meeting=meeting, user_id=user_id
                ).first()
                if att:
                    now = timezone.now()
                    att.left_at = now
                    if att.joined_at:
                        duration_secs = (now - att.joined_at).total_seconds()
                        att.duration_minutes = max(
                            att.duration_minutes or 0, int(duration_secs // 60)
                        )
                    att.save(
                        update_fields=["left_at", "duration_minutes", "updated_at"]
                    )

        elif event_type == "room_finished":
            if not meeting.is_completed:
                MeetingService.close_meeting(meeting)
