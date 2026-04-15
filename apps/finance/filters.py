from django_filters import rest_framework as filters
from .models import ExpenseRequest, Payroll


class ExpenseRequestFilter(filters.FilterSet):
    roles = filters.CharFilter(method='filter_by_user_roles', label="Rollar")

    class Meta:
        model = ExpenseRequest
        fields = {
            'user__direction': ['exact'],
            'status': ['exact'],
            'type': ['exact'],
            'expense_category': ['exact'],
            'amount': ['exact', 'gte', 'lte'],
            'created_at': ['date', 'date__gte', 'date__lte'],
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
            'user__direction': ['exact'],
            'month': ['exact', 'gte', 'lte'],
        }

    def filter_by_user_roles(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(user__roles__contains=[value])
