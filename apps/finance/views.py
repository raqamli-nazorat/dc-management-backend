from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.serializers import ValidationError as DRFValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework import viewsets, status, decorators, filters, permissions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from apps.notifications.models import Notification, NotificationType
from .models import ExpenseRequest, Status, Role, Payroll, Ledger, ExpenseCategory
from .serializers import ExpenseRequestSerializer, PayrollSerializer, LedgerSerializer, ExpenseCategorySerializer, \
    PayrollStatusUpdateSerializer


@extend_schema(tags=['Expense Category'])
class ExpenseCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ExpenseCategory.objects.filter(is_active=True)
    serializer_class = ExpenseCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None


@extend_schema(tags=['Expense'])
class ExpenseRequestViewSet(viewsets.ModelViewSet):
    queryset = ExpenseRequest.objects.filter(is_active=True)
    serializer_class = ExpenseRequestSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    filterset_fields = {
        'user__direction': ['exact'],
        'user__role': ['exact'],
        'status': ['exact'],
        'type': ['exact'],
        'expense_category': ['exact'],
        'amount': ['exact', 'gte', 'lte'],
        'created_at': ['date', 'date__gte', 'date__lte'],
    }

    search_fields = [
        'user__username'
    ]

    ordering_fields = ['created_at', 'amount', 'paid_at', 'user__username']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser or user.role in [Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR]:
            return self.queryset

        if user.role == Role.MANAGER:
            return self.queryset.filter(
                Q(user=user) |
                Q(user__employee_projects__manager=user) |
                Q(user__tester_projects__manager=user)
            ).distinct()

        return self.queryset.filter(user=user)

    def perform_create(self, serializer):
        if self.request.user.role in [Role.ADMIN, Role.AUDITOR]:
            raise PermissionDenied("Sizning rolingiz xarajatlar so'rovlarini yaratishga vakolatli emas.")
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        if self.get_object().status != Status.PENDING:
            raise PermissionDenied("Siz allaqachon ko'rib chiqilayotgan yoki to'langan so'rovni tahrirlay olmaysiz.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != Status.PENDING:
            raise PermissionDenied("Siz qayta ishlangan so'rovni o'chira olmaysiz.")
        instance.delete()

    @extend_schema(request=None)
    @decorators.action(detail=True, methods=['post'], url_path='pay')
    def pay_expense(self, request, pk=None):
        expense = self.get_object()

        if request.user.role != Role.ACCOUNTANT:
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
class PayrollViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payroll.objects.filter(is_active=True)
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    filterset_fields = {
        'is_confirmed': ['exact'],
        'user__role': ['exact', 'in'],
        'user__direction': ['exact'],
        'month': ['exact', 'gte', 'lte'],
    }

    search_fields = ['user__username']
    ordering_fields = ['month', 'total_amount', 'created_at']

    def get_serializer_class(self):
        if self.action == 'confirm_payroll':
            return PayrollStatusUpdateSerializer
        return PayrollSerializer

    def get_queryset(self):
        user = self.request.user

        if user.role in [Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR]:
            return self.queryset

        return self.queryset.filter(user=user)

    @extend_schema(
        request=PayrollStatusUpdateSerializer,
        responses={200: PayrollStatusUpdateSerializer}
    )
    @action(detail=True, methods=['patch'], url_path='confirm')
    def confirm_payroll(self, request, pk=None):
        payroll = self.get_object()
        user = request.user

        if user.role not in [Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT]:
            raise PermissionDenied("Sizda oyliklarni tasdiqlash huquqi yo'q.")

        serializer = self.get_serializer(payroll, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            serializer.save()

            if serializer.instance.is_confirmed:
                month_name = payroll.month.strftime("%B, %Y")

                Notification.objects.create(
                    user=payroll.user,
                    title="Oylik maosh tushdi!",
                    message=f"{month_name} oyi uchun maoshingiz tasdiqlandi va balansingizga qo'shildi.",
                    type=NotificationType.FINANCE,
                    extra_data={'payroll_id': payroll.id}
                )

        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict if hasattr(e, 'message_dict') else str(e))

        return Response({
            "message": "Oylik holati muvaffaqiyatli yangilandi va balansga qo'shildi.",
        }, status=status.HTTP_200_OK)


@extend_schema(tags=['Ledger'])
class LedgerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Ledger.objects.filter(is_active=True)
    serializer_class = LedgerSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['transaction_type', 'user', 'expense', 'payroll']
    search_fields = ['description']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user

        if user.role in [Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR]:
            return self.queryset

        return self.queryset.filter(user=user)
