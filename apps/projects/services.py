from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import TaskStatus, Task, MeetingAttendance, Meeting
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

    @staticmethod
    def send_task_notification(task, title, message):
        if task.assignee:
            Notification.objects.create(
                user=task.assignee,
                title=title,
                message=message,
                type=NotificationType.TASK,
                extra_data={'task_id': task.id}
            )

    @classmethod
    @transaction.atomic
    def change_status(cls, task, user, new_status, rejection_reason=None):
        current_status = task.status

        if not new_status or current_status == new_status:
            return task

        now = timezone.now()

        if user.has_role(Role.SUPERADMIN, Role.ADMIN) or task.project.manager == user:
            if new_status == TaskStatus.REJECTED:
                if current_status != TaskStatus.PRODUCTION:
                    raise PermissionDenied("Faqat 'Production' holatidagi vazifanigina rad etish mumkin.")

                if not rejection_reason or not rejection_reason.strip():
                    raise ValidationError("Vazifani rad etish uchun sabab ko'rsatish shart!")

                cls._apply_rejection_logic(task, rejection_reason, now)
                cls.send_task_notification(task, "Vazifangiz rad etildi", f"Sababi: {rejection_reason}")
                return task

            if cls.STATUS_ORDER.get(new_status, 0) < cls.STATUS_ORDER.get(current_status, 0):
                raise PermissionDenied("Statusni orqaga qaytara olmaysiz.")

            if new_status in [TaskStatus.DONE, TaskStatus.PRODUCTION] and task.started_at:
                elapsed = int((now - task.started_at).total_seconds() / 60)
                task.actual_minutes += max(0, elapsed)
                task.started_at = None

            task.status = new_status
            if new_status == TaskStatus.IN_PROGRESS:
                task.started_at = now

            task.save()

            if new_status == TaskStatus.CHECKED:
                cls.send_task_notification(task, "Vazifangiz tasdiqlandi", "Vazifa muvaffaqiyatli yakunlandi.")
            return task

        if task.assignee == user:
            employee_transitions = {
                TaskStatus.TODO: [TaskStatus.IN_PROGRESS],
                TaskStatus.IN_PROGRESS: [TaskStatus.DONE],
                TaskStatus.DONE: [TaskStatus.PRODUCTION],
                TaskStatus.REJECTED: [TaskStatus.IN_PROGRESS],
            }
            if new_status not in employee_transitions.get(current_status, []):
                raise PermissionDenied("Bu holatga o'tishga ruxsat yo'q yoki statusni orqaga qaytara olmaysiz.")

            if new_status == TaskStatus.DONE and task.started_at:
                elapsed = int((now - task.started_at).total_seconds() / 60)
                task.actual_minutes += max(0, elapsed)
                task.started_at = None

            if new_status == TaskStatus.IN_PROGRESS:
                task.started_at = now

            task.status = new_status
            task.save()
            return task

        if task.assignee is None and task.project.employees.filter(id=user.id).exists():
            if new_status == TaskStatus.IN_PROGRESS:
                if task.position_id and user.position_id != task.position_id:
                    raise PermissionDenied(f"Bu vazifa faqat '{task.position.name}' lavozimi uchun.")

                task.status = new_status
                task.assignee = user
                task.started_at = now
                task.save()
                return task
            raise PermissionDenied("Vazifani olish uchun uni 'Jarayonda' holatiga o'tkazing.")

        is_tester = task.project.testers.filter(id=user.id).exists()
        if is_tester:
            if current_status != TaskStatus.PRODUCTION:
                raise PermissionDenied("Faqat 'Production'dagi vazifalarni tekshira olasiz.")

            if new_status == TaskStatus.REJECTED:
                if not rejection_reason or not rejection_reason.strip():
                    raise ValidationError("Rad etish sababini yozing.")
                cls._apply_rejection_logic(task, rejection_reason, now)
                cls.send_task_notification(task, "Vazifa rad etildi", f"Tester: {rejection_reason}")
                return task

            if new_status == TaskStatus.CHECKED:
                task.status = TaskStatus.CHECKED
                task.save()
                cls.send_task_notification(task, "Tasdiqlandi", "Tester vazifani tasdiqladi.")
                return task

        raise PermissionDenied("Sizda statusni o'zgartirish huquqi yo'q.")

    @staticmethod
    def _apply_rejection_logic(task, reason, now):
        if task.status in [TaskStatus.DONE, TaskStatus.PRODUCTION, TaskStatus.CHECKED]:
            task.reopened_count += 1

        timestamp = timezone.localtime(now).strftime("%d.%m.%Y %H:%M")
        new_reason = f"[{timestamp}] {reason}"
        task.rejection_reason = f"{task.rejection_reason}\n\n{new_reason}" if task.rejection_reason else new_reason

        task.status = TaskStatus.IN_PROGRESS
        task.started_at = now
        task.save()


class MeetingService:
    @staticmethod
    def _send_meeting_notifications(meeting, members, organizer_id):
        notifications_to_bulk = []
        broadcast_data = []
        start_time_str = meeting.start_time.strftime('%d.%m.%Y %H:%M')

        for member in members:
            if member.id != organizer_id:
                msg = f"'{meeting.title}' mavzusida yig'ilish tayinlandi. Vaqti: {start_time_str}. Davomiyligi: {meeting.duration_minutes} daqiqa."

                notifications_to_bulk.append(Notification(
                    user=member,
                    title="Yangi uchrashuv belgilandi",
                    message=msg,
                    type=NotificationType.MEETING
                ))

                broadcast_data.append({
                    "user_id": member.id,
                    "title": "Yangi uchrashuv belgilandi",
                    "message": msg,
                    "type": "meeting",
                    "extra_data": {
                        "meeting_id": meeting.id,
                        "action": "open_meeting",
                        "project_id": meeting.project_id
                    }
                })

        if notifications_to_bulk:
            Notification.objects.bulk_create(notifications_to_bulk)

            from apps.notifications.tasks import mass_notification_sender
            transaction.on_commit(lambda: mass_notification_sender.delay(broadcast_data))

    @classmethod
    @transaction.atomic
    def handle_participants(cls, meeting, participants, organizer_id):
        if participants is None:
            return

        current_attendee_ids = set(MeetingAttendance.objects.filter(meeting=meeting).values_list('user_id', flat=True))
        new_participant_ids = {p.id for p in participants}

        MeetingAttendance.objects.filter(meeting=meeting).exclude(user_id__in=new_participant_ids).delete()

        to_add_ids = new_participant_ids - current_attendee_ids
        to_add = [p for p in participants if p.id in to_add_ids]

        if to_add:
            attendances = [
                MeetingAttendance(user=user, meeting=meeting)
                for user in to_add
            ]
            MeetingAttendance.objects.bulk_create(attendances)
            cls._send_meeting_notifications(meeting, to_add, organizer_id)

    @classmethod
    @transaction.atomic
    def create_meeting(cls, organizer, validated_data):
        participants = validated_data.pop('participants', [])
        meeting = Meeting.objects.create(organizer=organizer, **validated_data)
        cls.handle_participants(meeting, participants, organizer.id)

        if meeting.duration_minutes > 0:
            from .tasks import notify_meeting_end
            transaction.on_commit(lambda: notify_meeting_end.apply_async(
                args=[meeting.id],
                eta=meeting.start_time + timezone.timedelta(minutes=meeting.duration_minutes)
            ))

        return meeting

    @classmethod
    @transaction.atomic
    def close_meeting(cls, meeting):
        if meeting.is_completed:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": "Bu uchrashuv allaqachon tugagan."})

        meeting.is_completed = True
        meeting.save()

        absent_attendances = MeetingAttendance.objects.filter(meeting=meeting, is_attended=False).select_related('user')

        notifications_to_bulk = []
        broadcast_data = []

        for attendance in absent_attendances:
            msg = f"Siz '{meeting.title}' mavzusidagi uchrashuvda qatnashmadingiz. Sababini ko'rsatishingiz so'raladi."

            notifications_to_bulk.append(Notification(
                user_id=attendance.user.id,
                title="Yig'ilishda ishtirok etmadingiz.",
                message=msg,
                type=NotificationType.MEETING,
                extra_data={
                    "meeting_id": meeting.id,
                    "action": "open_meeting",
                    "project_id": meeting.project_id
                }
            ))

            broadcast_data.append({
                "user_id": attendance.user.id,
                "title": "Yig'ilishda ishtirok etmadingiz.",
                "message": msg,
                "type": NotificationType.MEETING,
                "extra_data": {
                    "meeting_id": meeting.id,
                    "action": "open_meeting",
                    "project_id": meeting.project_id
                }
            })

        if notifications_to_bulk:
            Notification.objects.bulk_create(notifications_to_bulk)

            from apps.notifications.tasks import mass_notification_sender
            transaction.on_commit(lambda: mass_notification_sender.delay(broadcast_data))

        return meeting
