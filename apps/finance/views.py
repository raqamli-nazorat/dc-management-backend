from django.db import transaction
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework import viewsets, status, decorators, filters, permissions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.notifications.models import Notification, NotificationType
from apps.notifications.tasks import mass_notification_sender
from apps.common.mixins import SoftDeleteMixin, RoleBasedQuerySetMixin

from .filters import ExpenseRequestFilter, PayrollFilter
from .models import ExpenseRequest, Status, Role, Payroll, Ledger, ExpenseCategory
from .serializers import ExpenseRequestSerializer, PayrollSerializer, LedgerSerializer, ExpenseCategorySerializer, \
    PayrollStatusUpdateSerializer

User = get_user_model()


@extend_schema(tags=['Expense Category'])
class ExpenseCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ExpenseCategory.objects.filter(is_active=True)
    serializer_class = ExpenseCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None


@extend_schema(tags=['Expense'])
class ExpenseRequestViewSet(SoftDeleteMixin, RoleBasedQuerySetMixin, viewsets.ModelViewSet):
    queryset = ExpenseRequest.objects.filter(is_active=True)
    serializer_class = ExpenseRequestSerializer
    permission_classes = [IsAuthenticated]
    full_access_roles = [Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ExpenseRequestFilter

    search_fields = [
        'user__username'
    ]

    ordering_fields = ['created_at', 'amount', 'paid_at', 'user__username']
    ordering = ['-created_at']
    
    def get_role_based_queryset(self, queryset, user):

        if user.has_role(Role.MANAGER):
            return queryset.filter(
                Q(user=user) |
                Q(user__employee_projects__manager=user) |
                Q(user__tester_projects__manager=user)
            ).distinct()

        return queryset.filter(user=user)

    def perform_create(self, serializer):
        expense = serializer.save(user=self.request.user)

        accountants = User.objects.filter(roles__contains=[Role.ACCOUNTANT], is_active=True)
        notifications_to_bulk = []
        broadcast_data = []

        for accountant in accountants:
            msg = f"{self.request.user.username} tomonidan {expense.amount:,.0f} miqdorida yangi xarajat so'rovi yaratildi."
            notifications_to_bulk.append(Notification(
                user=accountant,
                title="Yangi xarajat so'rovi",
                message=msg,
                type=NotificationType.FINANCE,
                extra_data={'expense_id': expense.id, 'action': 'view_expense'}
            ))

            broadcast_data.append({
                "user_id": accountant.id,
                "title": "Yangi xarajat so'rovi",
                "message": msg,
                "type": "finance",
                "extra_data": {'expense_id': expense.id, 'action': 'view_expense'}
            })

        if notifications_to_bulk:
            Notification.objects.bulk_create(notifications_to_bulk)
            transaction.on_commit(lambda: mass_notification_sender.delay(broadcast_data))

    def perform_update(self, serializer):
        if self.get_object().status != Status.PENDING:
            raise PermissionDenied("Siz allaqachon ko'rib chiqilayotgan yoki to'langan so'rovni tahrirlay olmaysiz.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != Status.PENDING:
            raise PermissionDenied("Siz qayta ishlangan so'rovni o'chira olmaysiz.")
        super().perform_destroy(instance)

    @extend_schema(request=None)
    @decorators.action(detail=True, methods=['post'], url_path='pay')
    def pay_expense(self, request, pk=None):
        expense = self.get_object()

        if not request.user.has_role(Role.ACCOUNTANT, Role.SUPERADMIN):
            raise PermissionDenied({'detail': "To'lovlarni amalga oshirish uchun faqat buxgalterlar vakolatli."})

        if expense.status != Status.PENDING:
            raise ValidationError({'status': "Faqat \"Kutilayotgan\" so'rovlarni \"To'langan\" deb belgilash mumkin."})

        expense.status = Status.PAID
        expense.accountant = request.user
        expense.paid_at = timezone.now()
        expense.save()

        Notification.objects.create(
            user=expense.user,
            title="To'lov amalga oshirildi!",
            message=f"Sizning {expense.amount:,.0f} miqdoridagi xarajatingiz to'landi. Iltimos, mablag'ni olganingizni tasdiqlang!",
            type=NotificationType.FINANCE,
            extra_data={'expense_id': expense.id, 'action': 'confirm_receipt'}
        )

        return Response({"message": "To'lov muvaffaqiyatli amalga oshirildi. Xodimning tasdiqlanishi kutilmoqda."},
                        status=status.HTTP_200_OK)

    @extend_schema(request=None)
    @decorators.action(detail=True, methods=['post'], url_path='confirm')
    def confirm_receipt(self, request, pk=None):
        expense = self.get_object()

        if expense.user != request.user:
            raise PermissionDenied(
                {'detail': "Faqat dastlabki so'rov beruvchi mablag'ni olganligini tasdiqlashi mumkin."})

        if expense.status != Status.PAID:
            raise ValidationError({'status': "So'rov tasdiqlanishidan oldin u “To'langan” holatida bo'lishi kerak."})

        expense.status = Status.CONFIRMED
        expense.save()

        if expense.accountant:
            Notification.objects.create(
                user=expense.accountant,
                title="Xarajat tasdiqlandi.",
                message=f"{expense.user.username} o'zining {expense.amount:,.0f} miqdoridagi xarajatini olganini tasdiqladi.",
                type=NotificationType.FINANCE,
                extra_data={'expense_id': expense.id}
            )

        return Response({"message": "Xarajatlar muvaffaqiyatli tasdiqlandi."},
                        status=status.HTTP_200_OK)


@extend_schema(tags=['Payroll'])
class PayrollViewSet(RoleBasedQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Payroll.objects.filter(is_active=True)
    permission_classes = [IsAuthenticated]
    full_access_roles = [Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PayrollFilter

    search_fields = ['user__username']
    ordering_fields = ['month', 'total_amount', 'created_at']

    def get_serializer_class(self):
        if self.action == 'confirm_payroll':
            return PayrollStatusUpdateSerializer
        return PayrollSerializer

    def get_role_based_queryset(self, queryset, user):
        return queryset.filter(user=user)

    @extend_schema(
        request=PayrollStatusUpdateSerializer,
        responses={200: PayrollStatusUpdateSerializer}
    )
    @action(detail=False, methods=['post'], url_path='confirm')
    def confirm_payroll(self, request):
        user = request.user

        if not user.has_role(Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT):
            raise PermissionDenied("Sizda oyliklarni tasdiqlash huquqi yo'q.")

        serializer = PayrollStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payroll_ids = serializer.validated_data['payroll_ids']

        payrolls = Payroll.objects.filter(id__in=payroll_ids, is_confirmed=False)

        if not payrolls.exists():
            return Response({"detail": "Hech qanday tasdiqlanishi kerak bo'lgan oylik topilmadi."},
                            status=status.HTTP_404_NOT_FOUND)

        notifications_to_bulk = []
        broadcast_data = []

        try:
            with transaction.atomic():
                for payroll in payrolls:
                    payroll.is_confirmed = True
                    payroll.save()

                    months = {
                        1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel",
                        5: "May", 6: "Iyun", 7: "Iyul", 8: "Avgust",
                        9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr"
                    }

                    month_number = payroll.month.month
                    month_name = months.get(month_number)

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

                if notifications_to_bulk:
                    Notification.objects.bulk_create(notifications_to_bulk)

                transaction.on_commit(lambda: mass_notification_sender.delay(broadcast_data))

        except Exception as e:
            return Response({"detail": f"Xatolik yuz berdi: {str(e)}"},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "message": f"{payrolls.count()} ta oylik muvaffaqiyatli tasdiqlandi va balansga o'tkazildi."
        }, status=status.HTTP_200_OK)


@extend_schema(tags=['Ledger'])
class LedgerViewSet(RoleBasedQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Ledger.objects.filter(is_active=True)
    serializer_class = LedgerSerializer
    permission_classes = [IsAuthenticated]
    full_access_roles = [Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['transaction_type', 'user', 'expense', 'payroll']
    search_fields = ['description']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']

    def get_role_based_queryset(self, queryset, user):
        return queryset.filter(user=user)
