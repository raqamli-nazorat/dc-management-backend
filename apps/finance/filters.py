from django_filters import rest_framework as filters
from .models import ExpenseRequest, Payroll


class ExpenseRequestFilter(filters.FilterSet):
    roles = filters.CharFilter(method='filter_by_user_roles', label="Rollar")
    my_requests = filters.BooleanFilter(method='filter_my_requests', label="Mening so'rovlarim")

    class Meta:
        model = ExpenseRequest
        fields = {
            'user__direction': ['exact'],
            'status': ['exact'],
            'type': ['exact'],
            'project': ['exact'],
            'expense_category': ['exact'],
            'amount': ['exact', 'gte', 'lte'],
            'created_at': ['date', 'date__gte', 'date__lte'],
            'paid_at': ['date', 'date__gte', 'date__lte'],
            'confirmed_at': ['date', 'date__gte', 'date__lte'],
        }

    def filter_by_user_roles(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(user__roles__contains=[value])

    def filter_my_requests(self, queryset, name, value):
        if value:
            return queryset.filter(user=self.request.user)
        return queryset


class PayrollFilter(filters.FilterSet):
    roles = filters.CharFilter(method='filter_by_user_roles', label="Rollar")

    class Meta:
        model = Payroll
        fields = {
            'is_confirmed': ['exact'],
            'user__direction': ['exact'],
            'month': ['exact', 'gte', 'lte'],
            'total_amount': ['exact', 'gte', 'lte'],
        }

    def filter_by_user_roles(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(user__roles__contains=[value])
