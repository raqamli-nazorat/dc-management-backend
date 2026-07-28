import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Any

import firebase_admin
from celery import shared_task, group
from firebase_admin import messaging
from .models import UserDevice

logger = logging.getLogger(__name__)

FCM_BATCH_SIZE = 500


@dataclass(frozen=True, slots=True)
class NotificationPayload:
    user_id: int
    title: str
    message: str
    notification_type: str = "system"
    extra_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        missing = [f for f in ("user_id", "title", "message") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Majburiy maydonlar yo'q: {missing}")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        nt = data.get("notification_type") or data.get("type") or "system"
        return cls(
            user_id=int(data["user_id"]),
            title=str(data["title"]),
            message=str(data["message"]),
            notification_type=str(nt),
            extra_data=data.get("extra_data") or {},
        )


@shared_task
def mass_notification_sender(raw_list):
    if not raw_list:
        return "Ro'yxat bo'sh"

    valid, skipped = [], 0
    for raw in raw_list:
        try:
            valid.append(send_single_notification_task.s(NotificationPayload.from_dict(raw).to_dict()))
        except Exception as e:
            logger.warning("Noto'g'ri payload o'tkazib yuborildi: %s | %s", raw, e)
            skipped += 1

    if not valid:
        return "Barcha yozuvlar noto'g'ri."

    group(valid).apply_async()
    return f"{len(valid)} ta yuborildi" + (f", {skipped} ta o'tkazib yuborildi." if skipped else ".")


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, max_retries=3)
def send_single_notification_task(self, raw):
    try:
        p = NotificationPayload.from_dict(raw)
    except Exception as e:
        logger.error("Notification payload xatosi: %s | %s", raw, e)
        return f"Xato payload: {e}"

    group(
        send_websocket_notification.s(raw),
        send_push_notification_task.s(p.user_id, p.title, p.message, p.notification_type, p.extra_data),
    ).apply_async()
    return f"User {p.user_id} uchun tasklar yuborildi."


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=60, max_retries=3)
def send_websocket_notification(self, data):
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    channel_layer = get_channel_layer()
    if not channel_layer:
        raise RuntimeError("Channel layer mavjud emas.")

    async_to_sync(channel_layer.group_send)(
        f"user_{data['user_id']}_notifications",
        {"type": "send_notification", "message": data}
    )


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, max_retries=3)
def send_push_notification_task(self, user_id, title, message, notification_type="system", extra_data=None):
    if not firebase_admin._apps:
        logger.info("FCM: Firebase ilovasi initsializatsiya qilinmagan, push yuborilmadi.")
        return "FCM sozlanmagan."

    tokens = list(
        UserDevice.objects
        .filter(user_id=user_id)
        .exclude(fcm_token__isnull=True)
        .exclude(fcm_token="")
        .values_list("fcm_token", flat=True)
    )

    if not tokens:
        return f"User {user_id} uchun tokenlar yo'q."

    fcm_data = {
        "payload": json.dumps(extra_data or {}, default=str),
        "type": str(notification_type)
    }
    success = failure = 0
    invalid_tokens = []

    for i in range(0, len(tokens), FCM_BATCH_SIZE):
        batch = tokens[i:i + FCM_BATCH_SIZE]
        try:
            multicast_msg = messaging.MulticastMessage(
                notification=messaging.Notification(title=title, body=message),
                data=fcm_data,
                tokens=batch,
            )
            if hasattr(messaging, 'send_each_for_multicast'):
                response = messaging.send_each_for_multicast(multicast_msg)
            else:
                response = messaging.send_multicast(multicast_msg)

            success += response.success_count
            failure += response.failure_count
            invalid_tokens += [batch[j] for j, r in enumerate(response.responses) if not r.success]
        except Exception as e:
            logger.error("FCM send_multicast xatosi (user=%s): %s", user_id, e)

    if invalid_tokens:
        deleted, _ = UserDevice.objects.filter(fcm_token__in=invalid_tokens).delete()
        logger.warning("FCM: %d ta eskirgan token o'chirildi | user=%s", deleted, user_id)

    logger.info("FCM: user=%s | ok=%d | fail=%d", user_id, success, failure)
    return f"FCM: {success} muvaffaqiyatli, {failure} muvaffaqiyatsiz"