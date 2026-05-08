from django_filters import rest_framework as filters

from apps.projects.filters import CharInFilter
from .models import User


class UserFilter(filters.FilterSet):
    roles = CharInFilter(method='filter_by_roles', label="Rollar")

    class Meta:
        model = User
        fields = {
            'region': ['exact'],
            'district': ['exact'],
            'position': ['exact'],
            'date_joined': ['exact', 'gte', 'lte'],
        }

    def filter_by_roles(self, queryset, name, value):
        if not value:
            return queryset

        return queryset.filter(roles__overlap=value)
