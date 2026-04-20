from django_filters import rest_framework as filters
from .models import Task


class TaskFilter(filters.FilterSet):
    my_tasks = filters.BooleanFilter(method='filter_my_tasks', label="Mening vazifalarim")

    class Meta:
        model = Task
        fields = ['status', 'priority', 'type', 'project']

    def filter_my_tasks(self, queryset, name, value):
        if value and getattr(self, 'request', None) and self.request.user.is_authenticated:
            return queryset.filter(assignee=self.request.user)
        return queryset
