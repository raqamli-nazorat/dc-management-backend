from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone

from apps.common.models import BaseModel
from apps.users.models import Role
from apps.projects.models import Project

User = get_user_model()


class Status(models.TextChoices):
    PENDING = 'pending', 'Kutilmoqda'
    PAID = 'paid', 'To\'landi'
    CONFIRMED = 'confirmed', 'Tasdiqlandi'
    CANCELLED = 'cancelled', 'Bekor qilindi'


class PaymentMethod(models.TextChoices):
    CASH = 'cash', 'Naqd pul'
    CARD = 'card', 'Karta raqam orqali'


class ExpenseType(models.TextChoices):
    WITHDRAWAL = 'withdrawal', 'Mablag\' chiqarish'
    COMPANY_EXPENSE = 'company', 'Kompaniya xarajatlari'
    OTHER = 'other', 'Boshqa xarajatlar'


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

    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expenses',
        verbose_name='Loyiha'
    )

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
                                   limit_choices_to={'roles__contains': [Role.ACCOUNTANT]},
                                   verbose_name='Hisobchi')

    paid_at = models.DateTimeField(null=True, blank=True, verbose_name='To\'langan vaqti')
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name='Tasdiqlangan vaqti')

    class Meta:
        verbose_name = "Xarajat so'rovi "
        verbose_name_plural = "Xarajat so'rovlari"
        ordering = ['-created_at']

    def clean(self):
        super().clean()

        if self.type == ExpenseType.COMPANY_EXPENSE and not self.project:
            raise ValidationError({
                'project': "Kompaniya xarajati uchun loyihani tanlash shart!"
            })

        if self.type != ExpenseType.COMPANY_EXPENSE and self.project:
            self.project = None

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
                status__in=[Status.PENDING, Status.PAID],
                is_active=True
            ).exists()

            if has_pending:
                raise ValidationError({'status': "Sizda hali yopilmagan so'rov bor!"})

            if self.type == ExpenseType.WITHDRAWAL and self.amount > self.user.balance:
                raise ValidationError({
                    'amount': f"Mablag‘ yetarli emas. Joriy balansingiz {self.user.balance}."
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new = self.pk is None

        if not is_new:
            old_instance = ExpenseRequest.objects.get(pk=self.pk)

            if old_instance.status != Status.CONFIRMED and self.status == Status.CONFIRMED:
                self.confirmed_at = timezone.now()

                if self.type == ExpenseType.WITHDRAWAL:
                    if self.user.balance < self.amount:
                        raise ValidationError("Balansda yetarli mablag' qolmagan!")

                    self.user.balance -= self.amount
                    self.user.save(update_fields=['balance'])

                Ledger.objects.create(
                    user=self.user,
                    expense=self,
                    amount=self.amount,
                    transaction_type=TransactionType.DEBIT,
                    description=f"{self.get_type_display()} tasdiqlandi. Sabab: {self.reason[:100]}"
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
        self.full_clean()
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

    is_confirmed = models.BooleanField(default=False, verbose_name='Tasdiqlandimi?')

    class Meta:
        verbose_name = "Ish haqi "
        verbose_name_plural = "Ish haqlari"
        unique_together = ('user', 'month')
        ordering = ['-month']

    def __str__(self):
        return self.user.get_username()

    def clean(self):
        super().clean()

        if self.pk:
            old_instance = Payroll.objects.get(pk=self.pk)

            if old_instance.is_confirmed and not self.is_confirmed:
                raise ValidationError({
                    'is_confirmed': "Tasdiqlangan oylikni bekor qilib bo'lmaydi."
                })

            if old_instance.is_confirmed:
                if (old_instance.fixed_salary != self.fixed_salary or
                        old_instance.kpi_bonus != self.kpi_bonus or
                        old_instance.penalty_amount != self.penalty_amount):
                    raise ValidationError(
                        "Tasdiqlangan oylik ma'lumotlarini tahrirlash taqiqlanadi!"
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        self.total_amount = self.fixed_salary + self.kpi_bonus - self.penalty_amount

        is_new = self.pk is None

        if not is_new:
            old_instance = Payroll.objects.get(pk=self.pk)

            if not old_instance.is_confirmed and self.is_confirmed:
                with transaction.atomic():
                    if self.total_amount != 0:
                        User.objects.filter(pk=self.user.pk).update(
                            balance=F('balance') + self.total_amount
                        )

                    month_label = self.month.strftime("%Y-%m")
                    ledger_entries = []

                    if self.fixed_salary > 0:
                        ledger_entries.append(Ledger(
                            user=self.user, payroll=self, amount=self.fixed_salary,
                            transaction_type=TransactionType.CREDIT, description=f"{month_label} oyi uchun asosiy maosh"
                        ))
                    if self.kpi_bonus > 0:
                        ledger_entries.append(Ledger(
                            user=self.user, payroll=self, amount=self.kpi_bonus,
                            transaction_type=TransactionType.CREDIT, description=f"{month_label} oyi uchun KPI bonusi"
                        ))
                    if self.penalty_amount > 0:
                        ledger_entries.append(Ledger(
                            user=self.user, payroll=self, amount=self.penalty_amount,
                            transaction_type=TransactionType.DEBIT,
                            description=f"{month_label} oyi uchun jami jarimalar"
                        ))

                    if ledger_entries:
                        Ledger.objects.bulk_create(ledger_entries)

        super().save(*args, **kwargs)
