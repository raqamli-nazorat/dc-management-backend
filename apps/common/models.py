from django.db import models


class BaseModel(models.Model):
    is_active = models.BooleanField(default=True, verbose_name='Faolmi?')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan vaqti')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Yangilangan vaqti')

    class Meta:
        abstract = True
