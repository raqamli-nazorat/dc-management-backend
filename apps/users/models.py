from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.users.utils import user_avatar_path, passport_path
from apps.applications.validators import phone_validator
from apps.applications.models import Region, Direction


class Role(models.TextChoices):
    SUPERADMIN = 'superadmin', 'Bosh administrator'
    ADMIN = 'admin', 'Administrator'
    MANAGER = 'manager', 'Menejer'
    EMPLOYEE = 'employee', 'Xodim'
    AUDITOR = 'auditor', 'Nazoratchi'
    ACCOUNTANT = 'accountant', 'Hisobchi'


class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, db_index=True, verbose_name="F.I.O")
    roles = ArrayField(models.CharField(max_length=20, choices=Role.choices), default=list, blank=True,
                       verbose_name="Rollari")

    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Viloyati")
    phone_number = models.CharField(validators=[phone_validator], max_length=13, blank=True,
                                    verbose_name="Telefon raqami")
    passport_series = models.CharField(max_length=9, blank=True, null=True, verbose_name="Passport seriyasi va raqami")

    passport_image = models.ImageField(upload_to=passport_path, null=True, blank=True, verbose_name="Passport rasmi")
    avatar = models.ImageField(upload_to=user_avatar_path, null=True, blank=True, verbose_name="Xodim avatari")

    direction = models.ForeignKey(Direction, on_delete=models.SET_NULL, null=True, blank=True,
                                  verbose_name='Yo\'nalishi')
    fixed_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Oylik maosh")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Balans")
    change_password = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Foydalanuvchi '
        verbose_name_plural = 'Foydalanuvchilar'

    def __str__(self):
        return f"{self.username}"

    def has_role(self, *allowed_roles):
        return bool(set(self.roles) & set(allowed_roles))
