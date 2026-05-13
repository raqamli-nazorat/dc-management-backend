from django_filters import rest_framework as filters

from .models import AuditLog


class AuditLogFilter(filters.FilterSet):
    class Meta:
        model = AuditLog
        fields = {
            'action': ['exact'],
            'table_name': ['exact', 'icontains'],
            'user': ['exact'],
            'record_id': ['exact'],
            'created_at': ['exact', 'gte', 'lte'],
        }