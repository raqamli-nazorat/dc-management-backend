from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel
from apps.users.models import Role

User = get_user_model()


class Status(models.TextChoices):
    PENDING = 'pending', 'Kutilmoqda'
    PAID = 'paid', 'To\'landi'
    CONFIRMED = 'confirmed', 'Tasdiqlandi'


class PaymentMethod(models.TextChoices):
    CASH = 'cash', 'Naqd pul'
    CARD = 'card', 'Karta'


class ExpenseType(models.TextChoices):
    WITHDRAWAL = 'withdrawal', 'Pulni yechib olish'
    COMPANY_EXPENSE = 'company', 'Kompaniya uchun'
    OTHER = 'other', 'Boshqa'


class TransactionType(models.TextChoices):
    DEBIT = 'debit', 'Chiqim'
    CREDIT = 'credit', 'Kirim'


class ExpenseCategory(BaseModel):
    title = models.CharField(max_length=255, unique=True, verbose_name='Nomi')

    class Meta:
        verbose_name = "Xarajatlar toifasi "
        verbose_name_plural = "Xarajatlar toifalari"
        ordering = ['title']

    def __str__(self):
        return self.title


class ExpenseRequest(BaseModel):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='expenses', verbose_name='Foydalanuvchi')

    type = models.CharField(max_length=20, choices=ExpenseType.choices, default=ExpenseType.WITHDRAWAL,
                            verbose_name='Turi')

    expense_category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, null=True, blank=True,
                                         related_name='expense_requests',
                                         verbose_name='Xarajat kategoriyasi'
                                         )

    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Miqdori')
    reason = models.TextField(verbose_name='Sababi')

    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.CARD,
                                      verbose_name='To\'lov turi')
    card_number = models.CharField(max_length=20, null=True, blank=True, verbose_name='Karta raqami')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name='Holati')
    accountant = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='approved_expenses',
                                   limit_choices_to={'role': Role.ACCOUNTANT},
                                   verbose_name='Hisobchi')

    paid_at = models.DateTimeField(null=True, blank=True, verbose_name='To\'langan vaqti')
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name='Tasdiqlangan vaqti')

    class Meta:
        verbose_name = "Xarajat so'rovi "
        verbose_name_plural = "Xarajat so'rovlari"
        ordering = ['-created_at']

    def clean(self):
        super().clean()

        if self.payment_method == PaymentMethod.CARD and not self.card_number:
            raise ValidationError({
                'card_number': "Karta orqali to'lash uchun siz karta raqamini kiritishingiz kerak!"
            })

        if self.payment_method == PaymentMethod.CASH and self.card_number:
            self.card_number = None

        if self.type == ExpenseType.OTHER and not self.expense_category:
            raise ValidationError({
                'expense_category': "Agar xarajat turi \"Boshqa\" bo'lsa, sabab toifasini tanlash shart!"
            })

        if self.type != ExpenseType.OTHER and self.expense_category:
            self.expense_category = None

        if not self.pk:
            has_pending = ExpenseRequest.objects.filter(
                user=self.user,
                status__in=[Status.PENDING, Status.PAID]
            ).exists()

            if has_pending:
                raise ValidationError({'status': "Sizda hali yopilmagan so'rov bor!"})

            if self.type == ExpenseType.WITHDRAWAL and self.amount > self.user.balance:
                raise ValidationError({
                    'amount': f"Mablag‘ yetarli emas. Joriy balansingiz {self.user.balance}."
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
                    description=f"{self.get_type_display()} tasdiqlandi: {self.reason[:50]}"
                )

        super().save(*args, **kwargs)

    def __str__(self):
        return self.user.get_username()


class Ledger(BaseModel):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='ledger_entries',
                             verbose_name='Foydalanuvchi')
    expense = models.ForeignKey(ExpenseRequest, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Xarajat')
    payroll = models.ForeignKey('Payroll', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Ish haqi')

    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Miqdori')
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices, verbose_name='Tranzaksiya turi')
    description = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Arxiv "
        verbose_name_plural = "Arxivlar"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError({'detail': "Arxiv yozuvlarini tahrirlab bo'lmaydi!"})
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError({'detail': "Arxiv yozuvlarini o'chirib bo'lmaydi!"})

    def __str__(self):
        return self.user.get_username()


class Payroll(BaseModel):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='payrolls', verbose_name='Foydalanuvchi')
    month = models.DateField(verbose_name='Oy')

    fixed_salary = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Oylik maosh')
    kpi_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='KPI bonusi')
    penalty_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Jarima miqdori')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False, verbose_name='Jami miqdori')

    tasks_completed = models.PositiveIntegerField(default=0, verbose_name='Bajarilgan vazifalar')
    deadline_missed = models.PositiveIntegerField(default=0, verbose_name='Muddatdan o\'tkazib yuborilganlar')
    bug_count = models.PositiveIntegerField(default=0, verbose_name='Xatolar')

    def save(self, *args, **kwargs):
        self.total_amount = self.fixed_salary + self.kpi_bonus - self.penalty_amount
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Ish haqi "
        verbose_name_plural = "Ish haqlari"
        unique_together = ('user', 'month')

    def __str__(self):
        return self.user.get_username()
