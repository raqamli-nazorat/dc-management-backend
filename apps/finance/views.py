from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework import viewsets, status, decorators, filters, permissions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from apps.common.mixins import SoftDeleteMixin, RoleBasedQuerySetMixin

from .services import ExpenseService, PayrollService
from .filters import ExpenseRequestFilter, PayrollFilter, LedgerFilter
from .models import ExpenseRequest, Status, Role, Payroll, Ledger, ExpenseCategory
from .serializers import ExpenseRequestSerializer, PayrollSerializer, LedgerSerializer, ExpenseCategorySerializer, \
    PayrollStatusUpdateSerializer, ExpenseCancelSerializer

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

    def get_role_based_queryset(self, queryset, user):
        if user.has_role(Role.MANAGER):
            return queryset.filter(
                Q(user=user) |
                Q(user__employee_projects__manager=user) |
                Q(user__tester_projects__manager=user)
            ).distinct()

        return queryset.filter(user=user)

    def perform_create(self, serializer):
        expense = ExpenseService.create_expense(self.request.user, serializer.validated_data)
        serializer.instance = expense

    def perform_update(self, serializer):
        if self.get_object().status != Status.PENDING:
            raise PermissionDenied("Siz allaqachon ko'rib chiqilayotgan yoki to'langan so'rovni tahrirlay olmaysiz.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != Status.PENDING:
            raise PermissionDenied("Siz qayta ishlangan so'rovni o'chira olmaysiz.")
        super().perform_destroy(instance)

    @extend_schema(request=ExpenseCancelSerializer)
    @decorators.action(detail=True, methods=['post'], url_path='cancel')
    def cancel_expense(self, request, pk=None):
        expense = self.get_object()

        serializer = ExpenseCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ExpenseService.cancel_expense(
            expense=expense,
            user=request.user,
            cancel_reason=serializer.validated_data['cancel_reason']
        )

        return Response(
            {"message": "Xarajat so'rovi muvaffaqiyatli bekor qilindi."},
            status=status.HTTP_200_OK
        )

    @extend_schema(request=None)
    @decorators.action(detail=True, methods=['post'], url_path='pay')
    def pay_expense(self, request, pk=None):
        ExpenseService.pay_expense(expense=self.get_object(), user=request.user)

        return Response({"message": "To'lov muvaffaqiyatli amalga oshirildi. Xodimning tasdiqlanishi kutilmoqda."},
                        status=status.HTTP_200_OK)

    @extend_schema(request=None)
    @decorators.action(detail=True, methods=['post'], url_path='confirm')
    def confirm_receipt(self, request, pk=None):
        ExpenseService.confirm_expense(expense=self.get_object(), user=request.user)

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
        if user.has_role(Role.MANAGER):
            return queryset.filter(
                Q(user=user) |
                Q(user__employee_projects__manager=user) |
                Q(user__tester_projects__manager=user)
            ).distinct()

        return queryset.filter(user=user)

    @extend_schema(
        request=PayrollStatusUpdateSerializer,
        responses={200: PayrollStatusUpdateSerializer}
    )
    @action(detail=False, methods=['post'], url_path='confirm')
    def confirm_payroll(self, request):
        serializer = PayrollStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payroll_ids = serializer.validated_data['payroll_ids']

        confirmed_count = PayrollService.confirm_payrolls(
            payroll_ids=payroll_ids,
            accountant_user=request.user
        )

        return Response({
            "message": f"{confirmed_count} ta oylik muvaffaqiyatli tasdiqlandi va balansga o'tkazildi."
        }, status=status.HTTP_200_OK)


@extend_schema(tags=['Ledger'])
class LedgerViewSet(RoleBasedQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Ledger.objects.filter(is_active=True)
    serializer_class = LedgerSerializer
    permission_classes = [IsAuthenticated]
    full_access_roles = [Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = LedgerFilter
    search_fields = ['description']
    ordering_fields = ['created_at', 'amount']

    def get_role_based_queryset(self, queryset, user):
        if user.has_role(Role.MANAGER):
            return queryset.filter(
                Q(user=user) |
                Q(user__employee_projects__manager=user) |
                Q(user__tester_projects__manager=user)
            ).distinct()

        return queryset.filter(user=user)
