import json
import logging
from celery import shared_task
from firebase_admin import messaging

from .models import UserDevice

logger = logging.getLogger(__name__)


@shared_task
def mass_notification_sender(notification_data_list):
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    channel_layer = get_channel_layer()

    for data in notification_data_list:
        group_name = f"user_{data['user_id']}_notifications"
        async_to_sync(channel_layer.group_send)(
            group_name, {"type": "send_notification", "message": data}
        )

        send_push_notification_task.delay(
            user_id=data['user_id'],
            title=data['title'],
            message=data['message'],
            notification_type=data['type'],
            extra_data=data['extra_data']
        )


@shared_task
def send_push_notification_task(user_id, title, message, notification_type='system', extra_data=None):
    device_tokens = list(UserDevice.objects.filter(user_id=user_id).values_list('fcm_token', flat=True))

    if not device_tokens:
        logger.info(f"User {user_id} uchun token topilmadi.")
        return "Tokenlar topilmadi."

    fcm_data = {
        "payload": json.dumps(extra_data or {}),
        "type": notification_type
    }

    multicast_message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=message,
        ),
        data=fcm_data,
        tokens=device_tokens,
    )

    response = messaging.send_multicast(multicast_message)

    if response.failure_count > 0:
        for index, res in enumerate(response.responses):
            if not res.success:
                invalid_token = device_tokens[index]
                UserDevice.objects.filter(fcm_token=invalid_token).delete()

    return f"Yuborildi: {response.success_count}, Xato: {response.failure_count}"
