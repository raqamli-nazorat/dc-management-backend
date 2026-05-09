from rest_framework.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone

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
        if task.assignee:
            deadline_str = task.deadline.strftime('%d.%m.%Y %H:%M')
            cls.send_task_notification(
                task.assignee,
                task,
                "Yangi vazifa biriktirildi",
                f"Sizga {task.title} nomli yangi vazifa topshirildi. Muddati: {deadline_str}"
            )

        manager = task.project.manager
        if manager and manager != user:
            cls.send_task_notification(
                manager,
                task,
                "Yangi vazifa yaratildi",
                f"Loyihangizda yangi vazifa yaratildi: {task.title}. Yaratuvchi: {user.get_full_name() or user.username}"
            )

        return task

    @classmethod
    @transaction.atomic
    def change_status(cls, task, user, new_status, rejection_reason=None):
        current_status = task.status
        if not new_status or current_status == new_status:
            return task

        now = timezone.now()

        if user.is_superuser or user.has_role(Role.ADMIN) or task.project.manager == user:
            return cls._handle_admin_manager_logic(task, user, new_status, rejection_reason, now)

        is_tester = task.project.testers.filter(id=user.id).exists()
        if is_tester:
            if task.assignee_id == user.id and new_status in [TaskStatus.REJECTED, TaskStatus.CHECKED]:
                raise PermissionDenied("O'zingiz topshirgan vazifani o'zingiz tekshira olmaysiz!")

            if new_status in [TaskStatus.REJECTED, TaskStatus.CHECKED]:
                return cls._handle_tester_logic(task, user, new_status, rejection_reason, now)

        if task.assignee == user:
            return cls._handle_assignee_logic(task, user, new_status, now)

        if task.assignee is None and task.project.employees.filter(id=user.id).exists():
            return cls._handle_claim_logic(task, user, new_status, now)

        raise PermissionDenied("Sizda ushbu vazifani statusini o'zgartirish huquqi yo'q.")

    @classmethod
    def _handle_admin_manager_logic(cls, task, user, new_status, rejection_reason, now):
        if new_status == TaskStatus.REJECTED:
            return cls._apply_rejection(task, rejection_reason, now, "Vazifa rad etildi")

        if cls.STATUS_ORDER.get(new_status, 0) < cls.STATUS_ORDER.get(task.status, 0):
            raise PermissionDenied("Statusni orqaga qaytara olmaysiz.")

        cls._update_task_time_and_status(task, new_status, now)
        if new_status == TaskStatus.CHECKED:
            cls.send_task_notification(task.assignee, task, "Vazifa tasdiqlandi", "Siz topshirgan vazifa tasdiqlandi.")
        return task

    @classmethod
    def _handle_tester_logic(cls, task, user, new_status, rejection_reason, now):
        if task.position_id and user.position_id != task.position_id:
            raise PermissionDenied(
                f"Siz faqat o'z lavozimingizga mos vazifalarni tekshira olasiz."
            )

        if task.status != TaskStatus.PRODUCTION:
            raise PermissionDenied("Faqat ishga tushurilgan vazifalarni tekshirish mumkin.")

        if new_status == TaskStatus.REJECTED:
            return cls._apply_rejection(task, rejection_reason, now, "Topshirilgan vazifa rad etildi")

        if new_status == TaskStatus.CHECKED:
            task.status = TaskStatus.CHECKED
            task.save()
            cls.send_task_notification(task.assignee, task, "Topshirilgan vazifa tasdiqlandi", "Siz topshirgan vazifa tasdiqlandi.")
            return task

    @classmethod
    def _handle_assignee_logic(cls, task, user, new_status, now):
        transitions = {
            TaskStatus.TODO: [TaskStatus.IN_PROGRESS],
            TaskStatus.IN_PROGRESS: [TaskStatus.DONE],
            TaskStatus.DONE: [TaskStatus.PRODUCTION],
            TaskStatus.REJECTED: [TaskStatus.IN_PROGRESS],
        }
        if new_status not in transitions.get(task.status, []):
            raise PermissionDenied("Bu bosqichga o'tishga ruxsat yo'q yoki status orqaga qaytaryapsiz.")

        cls._update_task_time_and_status(task, new_status, now)
        return task

    @classmethod
    def _handle_claim_logic(cls, task, user, new_status, now):
        if not user.has_role(Role.EMPLOYEE):
            raise PermissionDenied("Vazifani faqat xodimlar o'zlashtirishi mumkin.")

        if new_status != TaskStatus.IN_PROGRESS:
            raise PermissionDenied("Vazifani olish uchun uni jarayonga o'tkazing.")

        if task.position_id and user.position_id != task.position_id:
            raise PermissionDenied(f"Bu vazifa faqat {task.position.name} lavozimi uchun.")

        task.assignee = user
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = now
        task.save()
        return task

    @classmethod
    def _update_task_time_and_status(cls, task, new_status, now):
        if new_status in [TaskStatus.DONE, TaskStatus.PRODUCTION] and task.started_at:
            diff_seconds = (now - task.started_at).total_seconds()

            if diff_seconds >= 60:
                elapsed_minutes = int(diff_seconds / 60)
                task.actual_minutes += elapsed_minutes

            task.started_at = None

        task.status = new_status

        if new_status == TaskStatus.IN_PROGRESS:
            task.started_at = now

        task.save()

    @classmethod
    def _apply_rejection(cls, task, reason, now, title):
        if not reason or not reason.strip():
            raise ValidationError({'rejection_reason': "Rad etish sababini yozish shart!"})

        if task.status in [TaskStatus.DONE, TaskStatus.PRODUCTION, TaskStatus.CHECKED]:
            task.reopened_count += 1

        timestamp = timezone.localtime(now).strftime("%d.%m.%Y %H:%M")
        task.rejection_reason = (
                                    f"{task.rejection_reason}\n\n" if task.rejection_reason else "") + f"[{timestamp}] {reason}"

        task.status = TaskStatus.IN_PROGRESS
        task.started_at = now
        task.save()

        cls.send_task_notification(task.assignee, task, title, f"Sabab: {reason}")
        return task

    @staticmethod
    def send_task_notification(user, task, title, message):
        if user:
            Notification.objects.create(
                user=user,
                title=title,
                message=message,
                type=NotificationType.TASK,
                extra_data={'task_id': task.id}
            )


class MeetingService:
    @staticmethod
    def _send_meeting_notifications(meeting, members, organizer_id, title="Yangi yig'ilish belgilandi", msg_template=None):
        notifications_to_bulk = []
        broadcast_data = []
        start_time_str = meeting.start_time.strftime('%d.%m.%Y %H:%M')

        if msg_template is None:
            msg_template = f"{meeting.title} yig'ilish tayinlandi. Vaqti: {start_time_str}. Davomiyligi: {meeting.duration_minutes} daqiqa."

        for member in members:
            if member.id != organizer_id:
                notifications_to_bulk.append(Notification(
                    user=member,
                    title=title,
                    message=msg_template,
                    type=NotificationType.MEETING
                ))

                broadcast_data.append({
                    "user_id": member.id,
                    "title": title,
                    "message": msg_template,
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

        current_attendees = MeetingAttendance.objects.filter(meeting=meeting).select_related('user')
        current_attendee_ids = {a.user_id for a in current_attendees}
        new_participant_ids = {p.id for p in participants}
        
        if organizer_id not in new_participant_ids:
            new_participant_ids.add(organizer_id)

        to_remove_attendees = [a for a in current_attendees if a.user_id not in new_participant_ids]
        if to_remove_attendees:
            removed_users = [a.user for a in to_remove_attendees]
            MeetingAttendance.objects.filter(id__in=[a.id for a in to_remove_attendees]).delete()
            cls._send_meeting_notifications(
                meeting, 
                removed_users, 
                organizer_id, 
                title="Yig'ilishdan chiqarildingiz",
                msg_template=f"Siz '{meeting.title}' yig'ilishi qatnashchilari ro'yxatidan chiqarildingiz."
            )

        to_add_ids = new_participant_ids - current_attendee_ids

        if to_add_ids:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            to_add_users = User.objects.filter(id__in=to_add_ids)

            attendances = [
                MeetingAttendance(user=user, meeting=meeting)
                for user in to_add_users
            ]
            MeetingAttendance.objects.bulk_create(attendances)
            cls._send_meeting_notifications(meeting, to_add_users, organizer_id)

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
            raise ValidationError({"detail": "Bu yig'ilish allaqachon tugagan."})

        meeting.is_completed = True
        meeting.completed_at = timezone.now()
        meeting.save()

        absent_attendances = MeetingAttendance.objects.filter(meeting=meeting, is_attended=False).select_related('user')

        notifications_to_bulk = []
        broadcast_data = []

        for attendance in absent_attendances:
            msg = f"Siz {meeting.title} yig'ilishda qatnashmadingiz. Sababini ko'rsatishingiz so'raladi."

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

    @classmethod
    def notify_time_change(cls, meeting):
        participants = meeting.participants.all()
        start_time_str = meeting.start_time.strftime('%d.%m.%Y %H:%M')
        
        notifications_to_bulk = []
        broadcast_data = []
        
        msg = f"'{meeting.title}' yig'ilishi vaqti o'zgardi. Yangi vaqt: {start_time_str}. Davomiyligi: {meeting.duration_minutes} daqiqa."
        
        for member in participants:
            if member.id != meeting.organizer_id:
                notifications_to_bulk.append(Notification(
                    user=member,
                    title="Yig'ilish vaqti o'zgardi",
                    message=msg,
                    type=NotificationType.MEETING
                ))
                
                broadcast_data.append({
                    "user_id": member.id,
                    "title": "Yig'ilish vaqti o'zgardi",
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
