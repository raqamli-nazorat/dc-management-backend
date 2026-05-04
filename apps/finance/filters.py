from django_filters import rest_framework as filters
from .models import ExpenseRequest, Payroll, Ledger


class ExpenseRequestFilter(filters.FilterSet):
    roles = filters.CharFilter(method='filter_by_user_roles', label="Rollar")

    class Meta:
        model = ExpenseRequest
        fields = {
            'user__position': ['exact'],
            'status': ['exact'],
            'type': ['exact'],
            'project': ['exact'],
            'expense_category': ['exact'],
            'amount': ['exact', 'gte', 'lte'],
            'created_at': ['exact', 'gte', 'lte'],
            'paid_at': ['exact', 'gte', 'lte'],
            'confirmed_at': ['exact', 'gte', 'lte'],
        }

    def filter_by_user_roles(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(user__roles__contains=[value])


class PayrollFilter(filters.FilterSet):
    roles = filters.CharFilter(method='filter_by_user_roles', label="Rollar")

    class Meta:
        model = Payroll
        fields = {
            'is_confirmed': ['exact'],
            'user__position': ['exact'],
            'month': ['exact', 'gte', 'lte'],
            'total_amount': ['exact', 'gte', 'lte'],
            'penalty_amount': ['exact', 'gte', 'lte'],
        }

    def filter_by_user_roles(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(user__roles__contains=[value])


class LedgerFilter(filters.FilterSet):
    roles = filters.CharFilter(method='filter_by_user_roles', label="Rollar")

    class Meta:
        model = Ledger
        fields = {
            'user': ['exact'],
            'expense': ['exact'],
            'payroll': ['exact'],
            'transaction_type': ['exact'],
            'amount': ['exact', 'gte', 'lte'],
            'created_at': ['exact', 'gte', 'lte'],
        }

    def filter_by_user_roles(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(user__roles__contains=[value])
