from django.db import models
from django.contrib.auth import get_user_model
from apps.common.models import BaseModel

User = get_user_model()


class NotificationType(models.TextChoices):
    TASK = 'task', 'Vazifa'
    FINANCE = 'finance', 'Moliya'
    MEETING = 'meeting', 'Yig\'ilish'
    SYSTEM = 'system', 'Tizim xabari'
    ALERT = 'alert', 'Ogohlantirish'


class Notification(BaseModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        db_index=True,
        verbose_name='Qabul qiluvchi'
    )

    title = models.CharField(max_length=255, verbose_name='Sarlavha')
    message = models.TextField(verbose_name='Xabar matni')

    type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
        verbose_name='Turi'
    )

    extra_data = models.JSONField(null=True, blank=True, verbose_name="Qo'shimcha ma'lumot")

    is_read = models.BooleanField(default=False, verbose_name="O'qildimi?")

    class Meta:
        verbose_name = 'Bildirishnoma '
        verbose_name_plural = 'Bildirishnomalar'
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.title} ({'Oqilgan' if self.is_read else 'Oqilmagan'})"


class UserDevice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    fcm_token = models.TextField(unique=True)
    device_type = models.CharField(max_length=50, choices=[('ios', 'iOS'), ('android', 'Android'), ('web', 'Web')])
    device_id = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.device_type}"
