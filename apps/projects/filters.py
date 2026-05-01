from django.db.models import Q
from django_filters import rest_framework as filters
from .models import Task, Project, Meeting


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class TaskFilter(filters.FilterSet):
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


class ProjectFilter(filters.FilterSet):
    employee = filters.NumberFilter(method='filter_by_employee', label="Xodim")
    created_at_gte = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr='gte',
                                               label="Yaratilgan vaqti (dan)")
    created_at_lte = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr='lte',
                                               label="Yaratilgan vaqti (gacha)")

    deadline_gte = filters.IsoDateTimeFilter(field_name="deadline", lookup_expr='gte', label="Muddat (dan)")
    deadline_lte = filters.IsoDateTimeFilter(field_name="deadline", lookup_expr='lte', label="Muddat (gacha)")

    class Meta:
        model = Project
        fields = {
            'status': ['exact'],
            'manager': ['exact'],
            'is_deleted': ['exact'],
        }

    def filter_by_employee(self, queryset, name, value):
        return queryset.filter(
            Q(employees__id=value) | Q(testers__id=value)
        ).distinct()


class MeetingFilter(filters.FilterSet):
    start_date_gte = filters.DateFilter(field_name="start_time", lookup_expr='gte')
    start_date_lte = filters.DateFilter(field_name="start_time", lookup_expr='lte')

    class Meta:
        model = Meeting
        fields = {
            'project': ['exact'],
            'organizer': ['exact'],
            'is_completed': ['exact'],
        }
