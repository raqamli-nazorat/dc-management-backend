from django.contrib.auth import get_user_model
from django.db import models

from apps.common.models import BaseModel

User = get_user_model()


class ActionType(models.TextChoices):
    CREATE = 'create', 'Create'
    UPDATE = 'update', 'Update'
    DELETE = 'delete', "Delete"
    CONFIRM = 'confirm', 'Confirm'


class AuditLog(BaseModel):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs',
                             verbose_name='Foydalanuvchi')
    action = models.CharField(max_length=50, choices=ActionType.choices, verbose_name='Harakati')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP manzili')

    table_name = models.CharField(max_length=50, verbose_name='Jadval nomi')
    record_id = models.PositiveIntegerField(verbose_name='Yozuv raqami')

    old_values = models.JSONField(null=True, blank=True, verbose_name='Eski qiymati')
    new_values = models.JSONField(null=True, blank=True, verbose_name='Yangi qiymati')

    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='Vaqti')

    class Meta:
        verbose_name = 'Tarix yozuvi '
        verbose_name_plural = 'Tarix yozuvlari'

    def __str__(self):
        return self.table_name
