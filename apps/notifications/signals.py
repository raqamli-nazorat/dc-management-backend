from django.db.models.signals import post_save
from django.dispatch import receiver

from .tasks import mass_notification_sender
from .models import Notification


@receiver(post_save, sender=Notification)
def post_save_handler(sender, instance, created, **kwargs):
    if created:
        message_data = {
            "user_id": instance.user.id,
            "id": instance.id,
            "title": instance.title,
            "message": instance.message,
            "type": instance.type,
            "extra_data": instance.extra_data,
            "created_at": instance.created_at.isoformat()
        }

        mass_notification_sender.delay([message_data])