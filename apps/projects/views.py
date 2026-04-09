from django.db import transaction
from drf_spectacular.utils import extend_schema
from django_filters.rest_framework import DjangoFilterBackend

from django.db.models import Q
from rest_framework import viewsets, filters, permissions, parsers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response

from apps.users.models import Role
from apps.users.permissions import IsAdmin, IsManager, IsEmployee
from .models import Project, Task, TaskAttachment, Status, Meeting, MeetingAttendance
from .serializers import ProjectSerializer, TaskSerializer, TaskAttachmentSerializer, TaskStatusUpdateSerializer, \
    MeetingSerializer, MeetingAttendanceSerializer


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

        queryset = Project.objects.select_related('manager').prefetch_related('employees', 'testers')

        if user.role in [Role.SUPERADMIN, Role.ADMIN, Role.AUDITOR]:
            return queryset.all()

        return queryset.filter(
            Q(manager=user) |
            Q(testers=user) |
            Q(employees=user),
            is_active=True
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

    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            return [(IsAdmin | IsManager | IsEmployee)()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        queryset = Task.objects.select_related('project', 'assignee').prefetch_related('attachments')

        if user.role in [Role.SUPERADMIN, Role.ADMIN, Role.AUDITOR]:
            return queryset.all()

        if user.role == Role.MANAGER:
            return queryset.filter(project__manager=user, is_active=True)

        return queryset.filter(
            Q(assignee=user) | Q(project__testers=user, is_active=True)
        ).distinct()

    def perform_update(self, serializer):
        user = self.request.user
        task = self.get_object()
        new_status = serializer.validated_data.get('status')

        is_manager = task.project.manager == user or user.role in [Role.SUPERADMIN, Role.ADMIN]
        is_tester = task.project.testers.filter(id=user.id).exists()
        is_assignee = task.assignee == user

        if is_manager:
            serializer.save()
            return

        if is_assignee:
            allowed_for_employee = [Status.TODO, Status.IN_PROGRESS, Status.DONE]
            if new_status not in allowed_for_employee:
                raise PermissionDenied(
                    "Vazifani faqat \"Bajarildi\" holatiga o'tkazishingiz mumkin."
                    "Tekshirish menejer yoki sinovchi tomonidan amalga oshirilishi kerak."
                )
            serializer.save()
            return

        if is_tester:
            if is_assignee:
                raise PermissionDenied("Siz o'zingizga tayinlangan vazifa uchun sinovchi sifatida harakat qila olmaysiz.")

            serializer.save()
            return

        raise PermissionDenied("Sizda bu vazifaning holatini yangilash uchun ruxsat yo'q.")


@extend_schema(tags=['Task Attachments'])
class TaskAttachmentViewSet(viewsets.ModelViewSet):
    queryset = TaskAttachment.objects.all()
    serializer_class = TaskAttachmentSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        user = self.request.user
        queryset = TaskAttachment.objects.select_related('task__project', 'task__assignee')

        if user.role in [Role.SUPERADMIN, Role.ADMIN, Role.AUDITOR]:
            return queryset.all()

        if user.role == Role.MANAGER:
            return queryset.filter(task__project__manager=user, is_active=True)

        return queryset.filter(
            Q(task__assignee=user) |
            Q(task__project__testers=user),
            is_active=True
        ).distinct()

    def perform_create(self, serializer):
        task = serializer.validated_data.get('task')
        if task.status == Status.PRODUCTION:
            raise ValidationError("Ishlab chiqarishdagi vazifaga fayl qo'sha olmaysiz.")

        serializer.save()


@extend_schema(tags=['Meetings'])
class MeetingViewSet(viewsets.ModelViewSet):
    queryset = Meeting.objects.filter(is_active=True)
    serializer_class = MeetingSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [(IsAdmin | IsManager)()]
        return [permissions.IsAuthenticated()]

    @transaction.atomic
    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')

        meeting = serializer.save(organizer=self.request.user)
        project_members = set(project.employees.all()) | set(project.testers.all())

        attendances = [
            MeetingAttendance(user=user, meeting=meeting)
            for user in project_members
        ]

        MeetingAttendance.objects.bulk_create(attendances)

    @extend_schema(request=None)
    @action(detail=True, methods=['post'], permission_classes=[IsManager | IsAdmin])
    def close_meeting(self, request, pk=None):
        meeting = self.get_object()

        if meeting.is_completed:
            raise ValidationError({"detail": "Bu uchrashuv allaqachon tugagan."})

        meeting.is_completed = True
        meeting.save()

        absent_users = MeetingAttendance.objects.filter(meeting=meeting, is_attended=False)

        return Response({"message": "Uchrashuv yopildi va yo'q foydalanuvchilarga bildirishnomalar yuborildi."})


class MeetingAttendanceViewSet(viewsets.ModelViewSet):
    queryset = MeetingAttendance.objects.all()
    serializer_class = MeetingAttendanceSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_filter = ['meeting']

    def get_permissions(self):
        if self.action in ['update', 'partial_update']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

    def perform_update(self, serializer):
        user = self.request.user
        attendance = self.get_object()

        if user.role in [Role.SUPERADMIN, Role.ADMIN, Role.MANAGER]:
            serializer.save()
            return

        if attendance.user == user:
            if 'is_attended' in self.request.data:
                raise PermissionDenied("Siz o'zingizning ishtirok etish holatingizni o'zgartira olmaysiz.")

            serializer.save()
            return

        raise PermissionDenied("Sizda bu yozuvni tahrirlash uchun ruxsat yo'q.")
