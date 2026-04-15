from django.contrib.auth import get_user_model
from django.db import models

from apps.common.models import BaseModel

User = get_user_model()


class Todo(BaseModel):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='todos',
                             verbose_name="Eslatma egasi")
    title = models.CharField(max_length=255, verbose_name="Eslatma matni")
    is_done = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Eslatma "
        verbose_name_plural = "Eslatmalar"
        ordering = ['-created_at']

    def __str__(self):
        return self.title[:30]
