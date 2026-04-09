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
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=50, choices=ActionType.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    table_name = models.CharField(max_length=50)
    record_id = models.PositiveIntegerField()

    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.table_name
