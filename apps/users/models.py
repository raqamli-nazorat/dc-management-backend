from django.core.validators import RegexValidator
from django.contrib.auth.models import AbstractUser
from django.db import models

phone_regex = RegexValidator(
    regex=r'^\+998\d{9}$',
    message="The phone number must be in the format '+998XXXXXXXXX' and consist of 13 characters."
)


class Role(models.TextChoices):
    SUPERADMIN = 'superadmin', 'SuperAdmin'
    ADMIN = 'admin', 'Admin',
    MANAGER = 'manager', 'Manager',
    EMPLOYEE = 'employee', 'Employee',
    AUDITOR = 'auditor', 'Auditor',
    ACCOUNTANT = 'accountant', 'Accountant'


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)
    phone_number = models.CharField(max_length=15, null=True, blank=True, validators=[phone_regex])
    fixed_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    pin_code = models.CharField(max_length=128, null=True, blank=True)

    def __str__(self):
        return f"{self.get_full_name()} - {self.role}"