import logging
from collections import defaultdict
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import NotificationType, Notification
from apps.notifications.tasks import mass_notification_sender, send_single_notification_task
from .models import Project, ProjectStatus, Task, TaskStatus, Meeting

logger = logging.getLogger(__name__)


@shared_task
def update_project_tasks_on_unlock(project_id, working_seconds):
    try:
        project = Project.objects.get(id=project_id)
        tasks = list(project.tasks.all())

        if not tasks:
            return f"Loyiha (ID: {project_id}) uchun vazifalar topilmadi."

        now = timezone.now()
        td = timedelta(seconds=working_seconds)

        for task in tasks:
            task.deadline += td

            if task.status == TaskStatus.OVERDUE and task.deadline > now:
                task.status = TaskStatus.IN_PROGRESS
                task.was_overdue = False

        with transaction.atomic():
            Task.objects.bulk_update(tasks, ['deadline', 'status', 'was_overdue'], batch_size=500)

        return f"Loyiha (ID: {project_id}) uchun {len(tasks)} ta vazifa yangilandi."

    except Project.DoesNotExist:
        return f"Loyiha (ID: {project_id}) topilmadi."


@shared_task
def update_overdue_status_and_notify():
    now = timezone.now()
    notifications_to_create = []
    broadcast_data = []

    overdue_projects = list(Project.objects.filter(
        status=ProjectStatus.ACTIVE,
        is_hidden=False,
        is_deleted=False,
        is_active=True,
        deadline__lt=now
    ).only('id', 'title', 'manager_id', 'status', 'was_overdue'))

    for project in overdue_projects:
        project.status = ProjectStatus.OVERDUE
        project.was_overdue = True

        if project.manager_id:
            msg = f"'{project.title}' loyihasi rejadagidan kechikmoqda."

            notifications_to_create.append(Notification(
                user_id=project.manager_id,
                title="Loyiha muddati o'tdi",
                message=msg,
                type=NotificationType.ALERT
            ))

            broadcast_data.append({
                "user_id": project.manager_id,
                "title": "Loyiha muddati o'tdi",
                "message": msg,
                "type": NotificationType.ALERT,
                "extra_data": {"project_id": project.id, "action": "open_project"}
            })

    overdue_tasks = list(Task.objects.filter(
        status__in=[TaskStatus.TODO, TaskStatus.IN_PROGRESS],
        is_deleted=False,
        is_active=True,
        project__status=ProjectStatus.ACTIVE,
        deadline__lt=now
    ).select_related('project').only('id', 'title', 'project__manager_id', 'status', 'was_overdue'))

    for task in overdue_tasks:
        task.status = TaskStatus.OVERDUE
        task.was_overdue = True

        if task.project and task.project.manager_id:
            msg = f"'{task.title}' vazifasi belgilangan muddatdan kechikdi."

            notifications_to_create.append(Notification(
                user_id=task.project.manager_id,
                title="Vazifa muddati o'tdi",
                message=msg,
                type=NotificationType.ALERT
            ))
            broadcast_data.append({
                "user_id": task.project.manager_id,
                "title": "Vazifa muddati o'tdi",
                "message": msg,
                "type": NotificationType.ALERT,
                "extra_data": {"task_id": task.id, "action": "open_task"}
            })

    if overdue_projects:
        Project.objects.bulk_update(overdue_projects, ['status', 'was_overdue'], batch_size=500)

    if overdue_tasks:
        Task.objects.bulk_update(overdue_tasks, ['status', 'was_overdue'], batch_size=500)

    if notifications_to_create:
        Notification.objects.bulk_create(notifications_to_create, batch_size=500)
        mass_notification_sender.delay(broadcast_data)

    return f"{len(overdue_projects)} loyiha va {len(overdue_tasks)} vazifa yangilandi."


@shared_task
def send_morning_reminders():
    today = timezone.now().date()
    notifications_to_create = []
    broadcast_data = []

    remind_tasks = Task.objects.filter(
        deadline__date=today,
        assignee__isnull=False,
        status__in=[TaskStatus.TODO, TaskStatus.IN_PROGRESS]
    ).only('id', 'title', 'assignee_id')

    user_tasks = defaultdict(list)
    for task in remind_tasks.iterator(chunk_size=1000):
        user_tasks[task.assignee_id].append(task.title)

    for user_id, tasks in user_tasks.items():
        task_count = len(tasks)
        title = "Ertalabki vazifalar"
        message = (f"'{tasks[0]}' vazifasini bugun yakunlash shart!" if task_count == 1
                   else f"Bugun sizda {task_count} ta muhim vazifa bor.")

        notifications_to_create.append(Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=NotificationType.SYSTEM
        ))

        broadcast_data.append({
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": NotificationType.SYSTEM,
            "extra_data": {"filter": "today_tasks"}
        })

    if notifications_to_create:
        Notification.objects.bulk_create(notifications_to_create, batch_size=500)
        mass_notification_sender.delay(broadcast_data)

    return f"{len(user_tasks)} xodimga eslatmalar yuborildi."


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def notify_meeting_end(self, meeting_id, scheduled_eta_iso):
    try:
        from .models import Meeting
        from apps.notifications.models import Notification, NotificationType
        from apps.notifications.tasks import send_single_notification_task

        updated = Meeting.objects.filter(
            id=meeting_id,
            notification_eta=scheduled_eta_iso,
            notification_sent=False,
            is_active=True,
            is_completed=False,
        ).update(notification_sent=True)

        if not updated:
            return f"Meeting {meeting_id}: o'tkazib yuborildi (eski task yoki allaqachon yuborilgan)."

        meeting = Meeting.objects.select_related('organizer').get(id=meeting_id)

        title = "Yig'ilish tugadi"
        message = (
            f"Hurmatli {meeting.organizer.username}, '{meeting.title}' uchrashuvi uchun "
            f"belgilangan vaqt tugadi. Iltimos, ishtirokchilar ishtirokini tekshirib, "
            f"davomatni yakunlang."
        )

        Notification.objects.create(
            user=meeting.organizer,
            title=title,
            message=message,
            type=NotificationType.MEETING,
            extra_data={
                "meeting_id": meeting.id,
                "action": "close_meeting"
            }
        )

        send_single_notification_task.delay({
            "user_id": meeting.organizer.id,
            "title": title,
            "message": message,
            "type": "meeting",
            "extra_data": {
                "meeting_id": meeting.id,
                "action": "close_meeting",
                "project_id": meeting.project_id
            }
        })

        return f"Meeting {meeting_id} notification yuborildi → {meeting.organizer.username}"

    except Meeting.DoesNotExist:
        return f"Meeting {meeting_id} topilmadi."
    except Exception as exc:
        logger.error(f"Xatolik (ID: {meeting_id}): {exc}")
        raise self.retry(exc=exc)
