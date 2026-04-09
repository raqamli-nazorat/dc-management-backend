from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

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


class ExpenseType(models.TextChoices):
    WITHDRAWAL = 'withdrawal', 'Withdrawal'
    COMPANY_EXPENSE = 'company', 'Company'
    OTHER = 'other', 'Other'


class TransactionType(models.TextChoices):
    DEBIT = 'debit', 'Debit'
    CREDIT = 'credit', 'Credit'


class ExpenseCategory(BaseModel):
    title = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ['title']


class ExpenseRequest(BaseModel):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='expenses')

    type = models.CharField(max_length=20, choices=ExpenseType.choices, default=ExpenseType.WITHDRAWAL)

    expense_category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, null=True, blank=True,
                                         related_name='expense_requests'
                                         )

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

        if self.type == ExpenseType.OTHER and not self.expense_category:
            raise ValidationError({
                'expense_category': "If the expense type is 'Other', selecting a reason category is mandatory!"
            })

        if self.type != ExpenseType.OTHER and self.expense_category:
            self.expense_category = None

        if not self.pk:
            has_pending = ExpenseRequest.objects.filter(
                user=self.user,
                status__in=[Status.PENDING, Status.PAID]
            ).exists()

            if has_pending:
                raise ValidationError({'status': "You have a request that has not yet been closed!"})

            if self.type == ExpenseType.WITHDRAWAL and self.amount > self.user.balance:
                raise ValidationError({
                    'amount': f"Insufficient funds. Your current balance is {self.user.balance}."
                })

    def save(self, *args, **kwargs):
        self.full_clean()

        if self.pk:
            old_instance = ExpenseRequest.objects.get(pk=self.pk)

            if old_instance.status != Status.CONFIRMED and self.status == Status.CONFIRMED:
                self.confirmed_at = timezone.now()

                if self.type == ExpenseType.WITHDRAWAL:
                    self.user.balance -= self.amount
                    self.user.save(update_fields=['balance'])

                Ledger.objects.create(
                    expense=self,
                    user=self.user,
                    amount=self.amount,
                    transaction_type=TransactionType.DEBIT,
                    description=f"{self.get_type_display()} confirmed: {self.reason[:50]}"
                )

        super().save(*args, **kwargs)

    def __str__(self):
        return self.user.get_full_name()


class Ledger(BaseModel):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='ledger_entries')
    expense = models.ForeignKey(ExpenseRequest, on_delete=models.PROTECT, null=True, blank=True)
    payroll = models.ForeignKey('Payroll', on_delete=models.PROTECT, null=True, blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    description = models.CharField(max_length=255)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError({'detail': "Ledger entries cannot be edited!"})
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError({'detail': "Ledger entries cannot be deleted! Use reverse transactions instead."})

    def __str__(self):
        return self.user.get_full_name()


class Payroll(BaseModel):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='payrolls')
    month = models.DateField()

    fixed_salary = models.DecimalField(max_digits=12, decimal_places=2)
    kpi_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    penalty_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False)

    tasks_completed = models.PositiveIntegerField(default=0)
    deadline_missed = models.PositiveIntegerField(default=0)
    bug_count = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        self.total_amount = self.fixed_salary + self.kpi_bonus - self.penalty_amount
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ('user', 'month')

    def __str__(self):
        return self.user.get_full_name()
