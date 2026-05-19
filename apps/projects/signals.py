from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.db import transaction
from django.core.exceptions import ValidationError

from apps.notifications.models import Notification, NotificationType
from apps.projects.models import Project, ProjectStatus

User = get_user_model()


def send_system_notification(user, title, message, action, project_id):
    if user:
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            type=NotificationType.SYSTEM,
            extra_data={'project_id': project_id, 'action': action}
        )


@receiver(post_save, sender=Project)
def handle_project_post_save(sender, instance, created, **kwargs):
    if created:
        if instance.manager_id:
            send_system_notification(
                user=instance.manager,
                title="Yangi loyiha biriktirildi",
                message=f"Siz {instance.title} loyihasiga menejer etib tayinlandingiz.",
                action='manager_assigned',
                project_id=instance.id
            )
        return

    old_manager_id = getattr(instance, '_old_manager_id', None)
    if instance.manager_id and instance.manager_id != old_manager_id:
        send_system_notification(
            user=instance.manager,
            title="Yangi loyiha biriktirildi",
            message=f"Siz {instance.title} loyihasiga menejer etib tayinlandingiz.",
            action='manager_assigned',
            project_id=instance.id
        )

    _old_is_hidden = getattr(instance, '_old_is_hidden', None)

    if instance.is_hidden and not _old_is_hidden:
        send_system_notification(
            user=instance.created_by,
            title="Loyiha muzlatildi",
            message=f"{instance.title} loyihasi va undagi barcha vazifalar vaqtincha to'xtatildi.",
            action='freeze',
            project_id=instance.id
        )

    elif not instance.is_hidden and _old_is_hidden and getattr(instance, '_was_unfrozen', False):
        working_seconds = getattr(instance, '_unfreeze_working_seconds', 0)

        send_system_notification(
            user=instance.created_by,
            title="Loyiha faollashtirildi",
            message=f"{instance.title} loyihasi qayta faollashtirildi. Muddatlar surildi.",
            action='unfreeze',
            project_id=instance.id
        )

        if working_seconds > 0:
            from apps.projects.tasks import update_project_tasks_on_unlock
            transaction.on_commit(lambda: update_project_tasks_on_unlock.delay(instance.id, working_seconds))


@receiver(m2m_changed, sender=Project.employees.through)
def handle_project_employees_change(sender, instance, action, pk_set, **kwargs):
    if action in ["pre_add", "pre_remove"]:
        if instance.status in [ProjectStatus.COMPLETED, ProjectStatus.CANCELLED]:
            raise ValidationError(
                f"Loyiha {instance.get_status_display()} holatida. Xodimlarni tahrirlash taqiqlanadi!")

    if action == "post_add" and pk_set:
        if instance.status not in [ProjectStatus.PLANNING]:
            users = User.objects.filter(id__in=pk_set)
            for user in users:
                send_system_notification(
                    user=user,
                    title="Siz loyihaga qo'shildingiz",
                    message=f"Siz {instance.title} loyihasiga xodim sifatida qo'shildingiz.",
                    action='project_assigned',
                    project_id=instance.id
                )

    elif action == "post_remove" and pk_set:
        users = User.objects.filter(id__in=pk_set)
        for user in users:
            send_system_notification(
                user=user,
                title="Loyihadan chetlashtirildingiz",
                message=f"Siz {instance.title} loyihasi a'zoligidan chiqarib yuborildingiz.",
                action='project_removed',
                project_id=instance.id
            )


@receiver(m2m_changed, sender=Project.testers.through)
def handle_project_testers_change(sender, instance, action, pk_set, **kwargs):
    if action in ["pre_add", "pre_remove"]:
        if instance.status in [ProjectStatus.COMPLETED, ProjectStatus.CANCELLED]:
            raise ValidationError(
                f"Loyiha {instance.get_status_display()} holatida. "
                f"Xodimlar va sinovchilarni tahrirlash taqiqlanadi!")

    if action == "post_add" and pk_set:
        users = User.objects.filter(id__in=pk_set)
        for user in users:
            send_system_notification(
                user=user,
                title="Siz loyihaga qo'shildingiz",
                message=f"Siz {instance.title} loyihasiga sinovchi sifatida qo'shildingiz.",
                action='project_assigned',
                project_id=instance.id
            )

    elif action == "post_remove" and pk_set:
        users = User.objects.filter(id__in=pk_set)
        for user in users:
            send_system_notification(
                user=user,
                title="Loyihadan chetlashtirildingiz",
                message=f"Siz {instance.title} loyihasi sinovchilari qatoridan chiqarib yuborildingiz.",
                action='project_removed',
                project_id=instance.id
            )
