from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from django.contrib.auth import get_user_model

from apps.notifications.models import Notification, NotificationType
from .models import ExpenseRequest, Payroll, Status, Role

User = get_user_model()


class ExpenseService:
    @staticmethod
    def _create_notification(user, title, message, extra_data):
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            type=NotificationType.FINANCE,
            extra_data=extra_data
        )

    @classmethod
    @transaction.atomic
    def create_expense(cls, user, validated_data):
        expense = ExpenseRequest.objects.create(user=user, **validated_data)

        accountants = User.objects.filter(roles__contains=[Role.ACCOUNTANT], is_active=True)
        notifications_to_bulk = []
        broadcast_data = []

        for accountant in accountants:
            msg = f"{user.username} tomonidan {expense.amount:,.0f} miqdorida yangi xarajat so'rovi yaratildi."
            notifications_to_bulk.append(Notification(
                user=accountant,
                title="Yangi xarajat so'rovi",
                message=msg,
                type=NotificationType.FINANCE,
                extra_data={'expense_id': expense.id, 'action': 'open_expense'}
            ))

            broadcast_data.append({
                "user_id": accountant.id,
                "title": "Yangi xarajat so'rovi",
                "message": msg,
                "type": "finance",
                "extra_data": {'expense_id': expense.id, 'action': 'open_expense'}
            })

        if notifications_to_bulk:
            Notification.objects.bulk_create(notifications_to_bulk)

            from apps.notifications.tasks import mass_notification_sender
            transaction.on_commit(lambda: mass_notification_sender.delay(broadcast_data))

        return expense

    @classmethod
    @transaction.atomic
    def cancel_expense(cls, expense, user, cancel_reason):
        is_owner = expense.user == user
        is_accountant = user.has_role(Role.ACCOUNTANT)

        if not (is_owner or is_accountant):
            raise PermissionDenied("Sizda bu so'rovni bekor qilish huquqi yo'q.")

        if expense.status != Status.PENDING:
            raise ValidationError({'status': "Faqat 'Kutilmoqda' holatidagi so'rovni bekor qilish mumkin."})

        expense.status = Status.CANCELLED
        expense.cancel_reason = cancel_reason
        expense.cancelled_at = timezone.now()

        if is_accountant:
            expense.accountant = user

        expense.save()

        if not is_owner:
            cls._create_notification(
                user=expense.user,
                title="Xarajat so'rovi rad etildi",
                message=(
                    f"Sizning {expense.amount:,.0f} so'm miqdoridagi so'rovingiz "
                    f"hisobchi tomonidan rad etildi."
                ),
                extra_data={'expense_id': expense.id, 'action': "open_expense"}
            )

        return expense

    @classmethod
    @transaction.atomic
    def pay_expense(cls, expense, user):
        if not user.has_role(Role.ACCOUNTANT):
            raise PermissionDenied({'detail': "To'lovlarni amalga oshirish uchun faqat hisobchilar vakolatli."})

        if expense.status != Status.PENDING:
            raise ValidationError({'status': "Faqat \"Kutilayotgan\" so'rovlarni \"To'langan\" deb belgilash mumkin."})

        expense.status = Status.PAID
        expense.accountant = user
        expense.paid_at = timezone.now()
        expense.save()

        cls._create_notification(
            user=expense.user,
            title="Xarajat so'rovi to'landi",
            message=(
                f"Sizning {expense.amount:,.0f} so'm miqdoridagi xarajat so'rovingiz bo'yicha "
                f"to'lov amalga oshirildi. Iltimos, mablag'ni olganingizni tasdiqlang."
            ),
            extra_data={
                'expense_id': expense.id,
                'action': 'pay_receipt'
            }
        )

        return expense

    @classmethod
    @transaction.atomic
    def confirm_expense(cls, expense, user):
        if expense.user != user:
            raise PermissionDenied(
                {'detail': "Faqat dastlabki so'rov beruvchi mablag'ni olganligini tasdiqlashi mumkin."})

        if expense.status != Status.PAID:
            raise ValidationError({'status': "So'rov tasdiqlanishidan oldin u “To'langan” holatida bo'lishi kerak."})

        expense.status = Status.CONFIRMED
        expense.save()

        if expense.accountant:
            cls._create_notification(
                user=expense.accountant,
                title="Xarajat tasdiqlandi.",
                message=f"{expense.user.username} o'zining {expense.amount:,.0f} miqdoridagi xarajatini olganini tasdiqladi.",
                extra_data={'expense_id': expense.id, 'action': 'confirm_receipt'}
            )

        return expense


class PayrollService:
    @classmethod
    @transaction.atomic
    def confirm_payrolls(cls, payroll_ids, accountant_user):
        if not accountant_user.has_role(Role.ACCOUNTANT):
            raise PermissionDenied("Sizda oyliklarni tasdiqlash huquqi yo'q.")

        payrolls = Payroll.objects.filter(id__in=payroll_ids, is_confirmed=False)

        if not payrolls.exists():
            raise ValidationError({"detail": "Hech qanday tasdiqlanishi kerak bo'lgan oylik topilmadi."})

        notifications_to_bulk = []
        broadcast_data = []

        months = {
            1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel",
            5: "May", 6: "Iyun", 7: "Iyul", 8: "Avgust",
            9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr"
        }

        for payroll in payrolls:
            payroll.is_confirmed = True
            payroll.confirmed_at = timezone.now()
            payroll.accountant = accountant_user

            month_number = payroll.month.month
            month_name = months.get(month_number, "Noma'lum")

            msg = f"{month_name} oyi uchun maoshingiz tasdiqlandi."

            notifications_to_bulk.append(Notification(
                user=payroll.user,
                title="Oylik maosh tushdi!",
                message=msg,
                type=NotificationType.FINANCE
            ))

            broadcast_data.append({
                "user_id": payroll.user.id,
                "title": "Oylik maosh tushdi!",
                "message": msg,
                "type": "finance",
                "extra_data": {"payroll_id": payroll.id}
            })

        Payroll.objects.bulk_update(payrolls, fields=['is_confirmed', 'confirmed_at', 'accountant'])

        if notifications_to_bulk:
            Notification.objects.bulk_create(notifications_to_bulk)

            from apps.notifications.tasks import mass_notification_sender
            transaction.on_commit(lambda: mass_notification_sender.delay(broadcast_data))

        return payrolls.count()
