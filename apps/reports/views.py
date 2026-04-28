from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.contrib.auth import get_user_model
from django.db.models import Q
from apps.users.models import Role
from apps.projects.models import Project
from .serializers import UserComprehensiveReportSerializer, ProjectComprehensiveReportSerializer
from .filters import UserReportFilter, ProjectReportFilter

User = get_user_model()


@extend_schema(tags=['User Reports'])
class UserReportReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.filter(is_active=True)
    serializer_class = UserComprehensiveReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = UserReportFilter
    search_fields = ['username', 'phone_number', 'passport_series']
    ordering_fields = ['date_joined', 'balance', 'fixed_salary', 'username']
    ordering = ['-date_joined']

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        queryset = UserComprehensiveReportSerializer.setup_eager_loading(User.objects.filter(is_active=True))

        if not user or not user.is_authenticated:
            return queryset.none()

        if user.has_role(Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR):
            return queryset

        if user.has_role(Role.MANAGER):
            managed_employee_ids = Project.objects.filter(manager=user, is_active=True, is_deleted=False).values_list(
                'employees', flat=True)
            return queryset.filter(Q(id=user.id) | Q(id__in=managed_employee_ids)).distinct()

        return queryset.filter(id=user.id)


@extend_schema(tags=['Project Reports'])
class ProjectReportReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Project.objects.filter(is_active=True, is_deleted=False)
    serializer_class = ProjectComprehensiveReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProjectReportFilter
    search_fields = ['title', 'prefix', 'description']
    ordering_fields = ['deadline', 'project_price', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        queryset = ProjectComprehensiveReportSerializer.setup_eager_loading(
            Project.objects.filter(is_active=True, is_deleted=False))

        if not user or not user.is_authenticated:
            return queryset.none()

        if user.has_role(Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR):
            return queryset

        return queryset.filter(Q(manager=user) | Q(employees=user) | Q(testers=user)).distinct()
