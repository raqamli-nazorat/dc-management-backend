from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.response import Response

from apps.users.models import Role
from apps.projects.models import Project, Task
from apps.finance.models import ExpenseRequest, Payroll
from apps.users.serializers import UserShortSerializer
from .serializers import (
    UserComprehensiveReportSerializer,
    ProjectComprehensiveReportSerializer,
    ExpenseRequestReportSerializer,
    PayrollReportSerializer,
    TaskReportSerializer
)
from .filters import (
    UserReportFilter,
    ProjectReportFilter,
    ExpenseReportFilter,
    PayrollReportFilter,
    TaskReportFilter
)

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
            Project.objects.filter(is_active=True, is_deleted=False)
        )

        if not user or not user.is_authenticated:
            return queryset.none()

        if user.has_role(Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR):
            return queryset

        if user.has_role(Role.MANAGER):
            return queryset.filter(manager=user)

        if user.has_role(Role.EMPLOYEE):
            return queryset.filter(Q(employees=user) | Q(testers=user)).distinct()

        return queryset.none()

    @action(detail=False, methods=['get'], url_path='all-testers')
    def all_testers(self, request):
        projects = self.filter_queryset(self.get_queryset())

        testers = User.objects.filter(
            tester_projects__in=projects
        ).distinct().order_by('username')

        serializer = UserShortSerializer(testers, many=True)
        return Response(serializer.data)


@extend_schema(tags=['Expense Reports'])
class ExpenseReportReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ExpenseRequest.objects.all()
    serializer_class = ExpenseRequestReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ExpenseReportFilter
    search_fields = ['reason', 'cancel_reason', 'card_number']
    ordering_fields = ['created_at', 'amount', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        queryset = ExpenseRequestReportSerializer.setup_eager_loading(ExpenseRequest.objects.all())

        if not user or not user.is_authenticated:
            return queryset.none()

        if user.has_role(Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR):
            return queryset

        if user.has_role(Role.MANAGER):
            managed_employee_ids = Project.objects.filter(manager=user, is_active=True, is_deleted=False).values_list(
                'employees', flat=True)
            return queryset.filter(Q(user=user) | Q(user_id__in=managed_employee_ids)).distinct()

        return queryset.filter(user=user)


@extend_schema(tags=['Payroll Reports'])
class PayrollReportReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payroll.objects.all()
    serializer_class = PayrollReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PayrollReportFilter
    search_fields = ['user__username', 'accountant__username']
    ordering_fields = ['month', 'total_amount', 'created_at']
    ordering = ['-month', '-created_at']

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        queryset = PayrollReportSerializer.setup_eager_loading(Payroll.objects.all())

        if not user or not user.is_authenticated:
            return queryset.none()

        if user.has_role(Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR):
            return queryset

        if user.has_role(Role.MANAGER):
            managed_employee_ids = Project.objects.filter(manager=user, is_active=True, is_deleted=False).values_list(
                'employees', flat=True)
            return queryset.filter(Q(user=user) | Q(user_id__in=managed_employee_ids)).distinct()

        return queryset.filter(user=user)


@extend_schema(tags=['Task Reports'])
class TaskReportReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TaskReportFilter
    search_fields = ['title', 'uid', 'project__title', 'project__prefix']
    ordering_fields = ['deadline', 'created_at', 'task_price', 'priority']
    ordering = ['-created_at']

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        queryset = TaskReportSerializer.setup_eager_loading(Task.objects.all())

        if not user or not user.is_authenticated:
            return queryset.none()

        if user.has_role(Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR):
            return queryset

        if user.has_role(Role.MANAGER):
            managed_project_ids = Project.objects.filter(manager=user, is_active=True, is_deleted=False).values_list(
                'id', flat=True)

            return queryset.filter(project_id__in=managed_project_ids)

        return queryset.filter(
            Q(assignee=user) |
            Q(created_by=user) |
            Q(project__testers=user)
        ).distinct()
