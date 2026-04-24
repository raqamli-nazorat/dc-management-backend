import logging
from collections import defaultdict
from celery import shared_task
from django.utils import timezone
from django.db.models import Q

from apps.notifications.models import NotificationType, Notification
from apps.notifications.tasks import mass_notification_sender
from .models import Project, ProjectStatus, Task, TaskStatus

logger = logging.getLogger(__name__)


@shared_task
def update_overdue_status_and_notify():
    now = timezone.now()
    notifications_to_create = []
    broadcast_data = []

    overdue_projects = list(Project.objects.filter(
        status__in=[ProjectStatus.PLANNING, ProjectStatus.ACTIVE],
        deadline__lt=now
    ).only('id', 'title', 'manager_id'))

    for project in overdue_projects:
        project.status = ProjectStatus.OVERDUE
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
        deadline__lt=now
    ).select_related('project').only('id', 'title', 'project__manager_id'))

    for task in overdue_tasks:
        task.status = TaskStatus.OVERDUE
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
        Project.objects.bulk_update(overdue_projects, ['status'], batch_size=500)

    if overdue_tasks:
        Task.objects.bulk_update(overdue_tasks, ['status'], batch_size=500)

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
        Q(deadline__date=today) | Q(status=TaskStatus.OVERDUE),
        assignee__isnull=False
    ).exclude(
        status__in=[TaskStatus.DONE, TaskStatus.CHECKED, TaskStatus.PRODUCTION]
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
