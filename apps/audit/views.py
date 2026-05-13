from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from apps.users.permissions import IsAdmin, IsAuditor
from .serializers import AuditLogSerializer
from .filters import AuditLogFilter
from .models import AuditLog


@extend_schema(tags=['Audit Logs'])
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin | IsAuditor]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AuditLogFilter
    search_fields = ['user__username', 'ip_address', 'table_name']
    ordering_fields = ['timestamp']
