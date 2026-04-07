from drf_spectacular.utils import extend_schema
from django_filters.rest_framework import DjangoFilterBackend

from django.db.models import Q
from rest_framework import viewsets, filters, permissions, parsers
from rest_framework.exceptions import ValidationError

from apps.users.models import Role
from apps.users.permissions import IsAdmin, IsManager, IsEmployee
from .models import Project, Task, TaskAttachment, Status
from .serializers import ProjectSerializer, TaskSerializer, TaskAttachmentSerializer, TaskStatusUpdateSerializer


@extend_schema(tags=['Projects'])
class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]

    filterset_fields = ['status']
    search_fields = ['title', 'description']
    ordering_fields = ['status', 'deadline', 'start_date']
    ordering = ['-start_date']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user

        queryset = Project.objects.select_related('manager').prefetch_related('employees', 'auditors')

        if user.role in [Role.SUPERADMIN, Role.ADMIN]:
            return queryset.all()

        return queryset.filter(
            Q(manager=user) |
            Q(auditors=user) |
            Q(employees=user)
        ).distinct()


@extend_schema(tags=['Tasks'])
class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]

    filterset_fields = ['status', 'priority', 'type', 'project']
    search_fields = ['title', 'description']
    ordering_fields = ['deadline', 'priority', 'status', 'created_at']
    ordering = ['deadline']

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return TaskStatusUpdateSerializer
        return TaskSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Task.objects.select_related('project', 'assignee').prefetch_related('attachments')

        if user.role in [Role.SUPERADMIN, Role.ADMIN]:
            return queryset.all()

        if user.role == Role.MANAGER:
            return queryset.filter(project__manager=user)

        if user.role == Role.AUDITOR:
            return queryset.filter(project__auditors=user)

        return queryset.filter(assignee=user)


@extend_schema(tags=['Task Attachments'])
class TaskAttachmentViewSet(viewsets.ModelViewSet):
    queryset = TaskAttachment.objects.all()
    serializer_class = TaskAttachmentSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        user = self.request.user
        queryset = TaskAttachment.objects.select_related('task__project')

        if user.role in [Role.SUPERADMIN, Role.ADMIN]:
            return queryset.all()

        if user.role == Role.EMPLOYEE:
            return queryset.filter(task__assignee=user)

        if user.role in [Role.MANAGER, Role.AUDITOR]:
            return queryset.filter(
                Q(task__project__manager=user) |
                Q(task__project__auditors=user)
            ).distinct()

        return queryset.none()

    def perform_create(self, serializer):
        task = serializer.validated_data.get('task')
        if task.status == Status.PRODUCTION:
            raise ValidationError("You cannot add a file to a task in production.")

        serializer.save()
