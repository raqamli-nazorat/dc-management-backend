from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    SUPERADMIN = 'superadmin', 'Bosh administrator'
    ADMIN = 'admin', 'Administrator'
    MANAGER = 'manager', 'Menejer'
    EMPLOYEE = 'employee', 'Xodim'
    AUDITOR = 'auditor', 'Auditor'
    ACCOUNTANT = 'accountant', 'Hisobchi'


class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, db_index=True, verbose_name="F.I.O")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE, db_index=True,
                            verbose_name="Lavozim")
    fixed_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Oylik maosh")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Balans")
    change_password = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Foydalanuvchi '
        verbose_name_plural = 'Foydalanuvchilar'

    def __str__(self):
        return f"{self.username} - {self.role}"
