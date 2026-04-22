from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings

from apps.common.models import BaseModel
from .validators import (phone_validator, telegram_validator,
                         portfolio_validator, validate_resume)

User = settings.AUTH_USER_MODEL


class Region(BaseModel):
    name = models.CharField(max_length=255, unique=True, verbose_name="Nomi")
    is_application = models.BooleanField(default=False, verbose_name="Ariza uchun ham ishlatilsinmi?")

    class Meta:
        verbose_name = "Viloyat"
        verbose_name_plural = "Viloyatlar"
        ordering = ['name']

    def __str__(self):
        return self.name


class District(BaseModel):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='districts', verbose_name="Viloyat")
    name = models.CharField(max_length=255, verbose_name="Nomi")
    is_application = models.BooleanField(default=False, verbose_name="Ariza uchun ham ishlatilsinmi?")

    class Meta:
        verbose_name = "Tuman"
        verbose_name_plural = "Tumanlar"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.region.name})"


class Position(BaseModel):
    name = models.CharField(max_length=255, unique=True, verbose_name="Nomi")
    is_application = models.BooleanField(default=False, verbose_name="Ariza uchun ham ishlatilsinmi?")

    class Meta:
        verbose_name = "Lavozim"
        verbose_name_plural = "Lavozimlar"
        ordering = ['name']

    def __str__(self):
        return self.name


class ApplicationStatus(models.TextChoices):
    PENDING = 'pending', 'Kutilmoqda'
    ACCEPTED = 'accepted', 'Qabul qilindi'
    REJECTED = 'rejected', 'Rad etildi'


class Application(BaseModel):
    full_name = models.CharField(max_length=255, verbose_name="To'liq ism sharif")
    birth_date = models.DateField(verbose_name="Tug'ilgan sana")

    is_student = models.BooleanField(default=False, verbose_name="Talabami?")
    university = models.CharField(max_length=255, null=True, blank=True,
                                  verbose_name="O'qish joyi va kursi")

    region = models.ForeignKey(Region, on_delete=models.PROTECT,
                               related_name='applications', verbose_name="Viloyat")
    district = models.ForeignKey(District, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name='applications', verbose_name="Tuman")

    phone = models.CharField(max_length=20, validators=[phone_validator], verbose_name="Telefon raqami")
    telegram = models.CharField(max_length=255, null=True, blank=True, validators=[telegram_validator],
                                verbose_name="Telegram profil havolasi")

    position = models.ForeignKey(Position, on_delete=models.PROTECT,
                                  related_name='applications', verbose_name="Lavozim")

    resume = models.FileField(upload_to='applications/resumes/', validators=[validate_resume],
                              verbose_name="Rezyume (CV)")

    extra_info = models.TextField(null=True, blank=True, verbose_name="Qo'shimcha ma'lumot")
    portfolio = models.CharField(max_length=500, null=True, blank=True, validators=[portfolio_validator],
                                 verbose_name="Portfolio manzili")

    status = models.CharField(
        max_length=10,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING,
        db_index=True,
        verbose_name="Holati"
    )

    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_applications',
        verbose_name="Xulosa kiritgan xodim"
    )
    conclusion = models.TextField(null=True, blank=True, verbose_name="Xulosa")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Xulosa kiritilgan vaqt")

    class Meta:
        verbose_name = "Ariza"
        verbose_name_plural = "Arizalar"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} - {self.position}"

    def clean(self):
        super().clean()
        if self.district and self.region:
            if self.district.region_id != self.region_id:
                raise ValidationError({
                    'district': "Tanlangan tuman ushbu viloyatga tegishli emas!"
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
