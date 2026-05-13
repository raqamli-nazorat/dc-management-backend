from django.db.models import Q
from rest_framework import viewsets, filters
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from apps.users.models import Role
from apps.common.mixins import RoleBasedQuerySetMixin
from .serializers import AuditLogSerializer
from .filters import AuditLogFilter
from .models import AuditLog


@extend_schema(tags=['Audit Logs'])
class AuditLogViewSet(RoleBasedQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    full_access_roles = [Role.ADMIN, Role.AUDITOR]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AuditLogFilter
    search_fields = ['user__username', 'ip_address', 'table_name']
    ordering_fields = ['created_at']

    def get_role_based_queryset(self, queryset, user):
        if user.has_role(Role.MANAGER):
            return queryset.filter(
                Q(user=user) |
                Q(user__employee_projects__manager=user) |
                Q(user__tester_projects__manager=user)
            ).distinct()

        return queryset.filter(user=user)
