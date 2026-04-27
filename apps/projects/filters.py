from django_filters import rest_framework as filters
from .models import Task, Project, Meeting


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class TaskFilter(filters.FilterSet):
    my_tasks = filters.BooleanFilter(method='filter_my_tasks', label="Mening vazifalarim")

    project = NumberInFilter(field_name='project_id', lookup_expr='in', label="Loyihalar")
    created_by = NumberInFilter(field_name='created_by_id', lookup_expr='in', label="Yaratuvchilar")
    status = CharInFilter(field_name='status', lookup_expr='in', label="Holatlar")
    priority = CharInFilter(field_name='priority', lookup_expr='in', label="Darajalar")
    type = CharInFilter(field_name='type', lookup_expr='in', label="Turlar")
    position = NumberInFilter(field_name='position_id', lookup_expr='in', label="Lavozimlar")
    sprint = NumberInFilter(field_name='sprint', lookup_expr='in', label="Sprint")

    created_from = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte', label="Yaratilgan (Dan)")
    created_to = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte', label="Yaratilgan (Gacha)")

    deadline_from = filters.DateTimeFilter(field_name='deadline', lookup_expr='gte', label="Muddati (Dan)")
    deadline_to = filters.DateTimeFilter(field_name='deadline', lookup_expr='lte', label="Muddati (Gacha)")

    started_from = filters.DateTimeFilter(field_name='started_at', lookup_expr='gte', label="Boshlangan (Dan)")
    started_to = filters.DateTimeFilter(field_name='started_at', lookup_expr='lte', label="Boshlangan (Gacha)")

    class Meta:
        model = Task
        fields = ['status', 'priority', 'type', 'project', 'created_by', 'position', 'sprint']

    def filter_my_tasks(self, queryset, name, value):
        if value and getattr(self, 'request', None) and self.request.user.is_authenticated:
            return queryset.filter(assignee=self.request.user)
        return queryset

    
class ProjectFilter(filters.FilterSet):
    class Meta:
        model = Project
        fields = {
            'status': ['exact'],
            'manager': ['exact'],
            'is_active': ['exact'],
            'deadline': ['date', 'date__gte', 'date__lte'],
            'created_at': ['date', 'date__gte', 'date__lte'],
        }


class MeetingFilter(filters.FilterSet):
    class Meta:
        model = Meeting
        fields = {
            'project': ['exact'],
            'organizer': ['exact'],
            'is_completed': ['exact'],
            'start_time': ['date', 'date__gte', 'date__lte'],
        }