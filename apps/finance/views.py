from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework import viewsets, status, decorators, filters, permissions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from .models import ExpenseRequest, Status, Role, Payroll, Ledger, ExpenseCategory
from .serializers import ExpenseRequestSerializer, PayrollSerializer, LedgerSerializer, ExpenseCategorySerializer


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

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser or user.role in [Role.SUPERADMIN, Role.ACCOUNTANT, Role.AUDITOR]:
            return self.queryset

        return self.queryset.filter(user=user)

    def perform_create(self, serializer):
        if self.request.user.role in [Role.ADMIN, Role.AUDITOR]:
            raise PermissionDenied("Your role is not authorized to create expense requests.")
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        if self.get_object().status != Status.PENDING:
            raise PermissionDenied("You cannot edit a request that is already being processed or paid.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != Status.PENDING:
            raise PermissionDenied("You cannot delete a processed request.")
        instance.delete()

    @extend_schema(request=None)
    @decorators.action(detail=True, methods=['post'], url_path='pay')
    def pay_expense(self, request, pk=None):
        expense = self.get_object()

        if request.user.role != Role.ACCOUNTANT:
            raise PermissionDenied({'detail': "Only accountants are authorized to process payments."})

        if expense.status != Status.PENDING:
            raise ValidationError({'status': "Only 'Pending' requests can be marked as 'Paid'."})

        expense.status = Status.PAID
        expense.accountant = request.user
        expense.paid_at = timezone.now()
        expense.save()
        return Response({"message": "Payment processed successfully. Awaiting employee confirmation."},
                        status=status.HTTP_200_OK)

    @extend_schema(request=None)
    @decorators.action(detail=True, methods=['post'], url_path='confirm')
    def confirm_receipt(self, request, pk=None):
        expense = self.get_object()

        if expense.user != request.user:
            raise PermissionDenied({'detail': "Only the original requestor can confirm receipt of funds."})

        if expense.status != Status.PAID:
            raise ValidationError({'status': "The request must be in 'Paid' status before it can be confirmed."})

        expense.status = Status.CONFIRMED
        expense.save()

        return Response({"message": "Expense confirmed successfully and archived in Ledger."},
                        status=status.HTTP_200_OK)


@extend_schema(tags=['Payroll'])
class PayrollViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payroll.objects.filter(is_active=True)
    serializer_class = PayrollSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role in [Role.SUPERADMIN, Role.ACCOUNTANT, Role.AUDITOR]:
            return self.queryset

        return self.queryset.filter(user=user)


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

        if user.role in [Role.SUPERADMIN, Role.ACCOUNTANT, Role.AUDITOR]:
            return self.queryset

        return self.queryset.filter(user=user)
