from django.contrib.auth import get_user_model
from django.db import models

from apps.common.models import BaseModel

User = get_user_model()


class TodoColor(models.TextChoices):
    RED = 'red', 'Qizil'
    GREEN = 'green', 'Yashil'
    BLUE = 'blue', 'Ko\'k'
    YELLOW = 'yellow', 'Sariq'


class Todo(BaseModel):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='todos',
                             verbose_name="Egasi")
    title = models.CharField(max_length=255, verbose_name="Vazifa nomi")
    color = models.CharField(max_length=20, choices=TodoColor.choices, default=TodoColor.BLUE, verbose_name="Rangi")
    deadline = models.DateField(null=True, blank=True, verbose_name="Muddati")
    is_done = models.BooleanField(default=False, verbose_name="Bajarildimi?")

    class Meta:
        verbose_name = "Vazifa "
        verbose_name_plural = "Vazifalar"
        ordering = ['-created_at']

    def __str__(self):
        return self.title[:30]


class TodoItem(BaseModel):
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name='items', verbose_name="Vazifa")
    title = models.CharField(max_length=255, verbose_name="Nomi")
    is_done = models.BooleanField(default=False, verbose_name="Bajarildimi?")

    class Meta:
        verbose_name = "Kichik vazifa "
        verbose_name_plural = "Kichik vazifalar"
        ordering = ['created_at']

    def __str__(self):
        return self.title[:30]
