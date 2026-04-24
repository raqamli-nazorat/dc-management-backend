import django_filters
from django_filters import rest_framework as filters
from .models import User

class UserFilter(filters.FilterSet):
    roles = filters.CharFilter(method='filter_by_roles')

    class Meta:
        model = User
        fields = ['region', 'position']

    def filter_by_roles(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(roles__contains=[value])