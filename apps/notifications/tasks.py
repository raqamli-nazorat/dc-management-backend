import json
import logging
from celery import shared_task, group
from firebase_admin import messaging
from .models import UserDevice

logger = logging.getLogger(__name__)


@shared_task
def mass_notification_sender(notification_data_list):
    if not notification_data_list:
        return "Ro'yxat bo'sh"

    task_signatures = [send_single_notification_task.s(data) for data in notification_data_list]

    task_chunks = group(task_signatures).skew(step=1).chunks(50)
    task_chunks.apply_async()

    return f"{len(notification_data_list)} xabarlar bo'laklarga bo'lindi."


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_single_notification_task(self, data):
    send_websocket_notification.delay(data)

    send_push_notification_task.delay(
        user_id=data['user_id'],
        title=data['title'],
        message=data['message'],
        notification_type=data.get('type', 'system'),
        extra_data=data.get('extra_data', {})
    )


@shared_task
def send_websocket_notification(data):
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    try:
        channel_layer = get_channel_layer()
        group_name = f"user_{data['user_id']}_notifications"
        async_to_sync(channel_layer.group_send)(
            group_name, {"type": "send_notification", "message": data}
        )
    except Exception as e:
        logger.error(f"WS Error: {e}")


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_push_notification_task(self, user_id, title, message, notification_type='system', extra_data=None):
    device_tokens = list(UserDevice.objects.filter(user_id=user_id).values_list('fcm_token', flat=True))

    if not device_tokens:
        return f"Foydalanuvchi {user_id} uchun tokenlar yo'q."

    fcm_data = {
        "payload": json.dumps(extra_data or {}),
        "type": notification_type
    }

    multicast_message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=message),
        data=fcm_data,
        tokens=device_tokens,
    )

    response = messaging.send_multicast(multicast_message)

    if response.failure_count > 0:
        for index, res in enumerate(response.responses):
            if not res.success:
                invalid_token = device_tokens[index]
                UserDevice.objects.filter(fcm_token=invalid_token).delete()

    return f"FCM: {response.success_count} muvaffaqiyatli, {response.failure_count} muvaffaqiyatsiz"
