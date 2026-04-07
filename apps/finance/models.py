from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import BaseModel
from apps.users.models import Role

User = get_user_model()


class Status(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PAID = 'paid', 'Paid'
    CONFIRMED = 'confirmed', 'Confirmed'


class PaymentMethod(models.TextChoices):
    CASH = 'cash', 'Cash'
    CARD = 'card', 'Card'


class TransactionType(models.TextChoices):
    DEBIT = 'debit', 'Debit'
    CREDIT = 'credit', 'Credit'


class ExpenseRequest(BaseModel):
    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expenses',
                                 limit_choices_to={'role': Role.EMPLOYEE})
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()

    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.CARD)
    card_number = models.CharField(max_length=20, null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    accountant = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='approved_expenses',
                                   limit_choices_to={'role': Role.ACCOUNTANT})

    paid_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        super().clean()

        if self.payment_method == PaymentMethod.CARD and not self.card_number:
            raise ValidationError({
                'card_number': "To pay by card, you must enter the card number!"
            })

        if self.payment_method == PaymentMethod.CASH and self.card_number:
            self.card_number = None

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Ledger(BaseModel):
    expense = models.ForeignKey(ExpenseRequest, on_delete=models.PROTECT, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)

    description = models.CharField(max_length=255)
