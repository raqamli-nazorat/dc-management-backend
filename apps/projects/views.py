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

from apps.common.mixins import SoftDeleteMixin, RoleBasedQuerySetMixin, TrashMixin

from .services import TaskService, MeetingService
from .filters import TaskFilter, ProjectFilter, MeetingFilter
from .models import Project, ProjectStatus, Task, TaskAttachment, TaskStatus, Meeting, MeetingAttendance, \
    TaskRejectionFile
from .serializers import (ProjectShortSerializer, ProjectSerializer, TaskSerializer,
                          TaskAttachmentSerializer, \
                          TaskStatusUpdateSerializer, MeetingSerializer, MeetingAttendanceSerializer,
                          TaskRejectionFileSerializer)


@extend_schema(tags=['Project Shorts'])
class ProjectShortViewSet(RoleBasedQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Project.objects.filter(is_deleted=False, is_active=True).select_related('manager').prefetch_related(
        'employees', 'testers')
    serializer_class = ProjectShortSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]

    filterset_fields = ['prefix', 'status']
    search_fields = ['title', 'description']
    ordering_fields = ['status', 'deadline', 'created_at']

    full_access_roles = [Role.ADMIN, Role.AUDITOR]

    def get_role_based_queryset(self, queryset, user):
        base_filters = {
            'is_hidden': False
        }

        excluded_statuses = [
            ProjectStatus.COMPLETED,
            ProjectStatus.CANCELLED,
            ProjectStatus.PLANNING
        ]

        if user.has_role(Role.MANAGER):
            return queryset.filter(
                manager=user,
                **base_filters
            ).exclude(status__in=excluded_statuses).distinct()

        if user.has_role(Role.EMPLOYEE):
            return queryset.filter(
                Q(testers=user) | Q(employees=user),
                **base_filters
            ).exclude(status__in=excluded_statuses).distinct()

        return queryset.none()


@extend_schema(tags=['Projects'])
class ProjectViewSet(RoleBasedQuerySetMixin, TrashMixin, viewsets.ModelViewSet):
    queryset = Project.objects.select_related('manager').prefetch_related('employees', 'testers')
    serializer_class = ProjectSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]

    filterset_class = ProjectFilter
    search_fields = ['title', 'description']
    ordering_fields = ['status', 'deadline', 'created_at']
    full_access_roles = [Role.ADMIN, Role.AUDITOR]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'restore', 'hard_delete']:
            return [IsAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'action', None) in ['trash', 'restore', 'hard_delete']:
            return queryset.filter(is_deleted=True)
        return queryset.filter(is_deleted=False, is_active=True)

    def get_role_based_queryset(self, queryset, user):
        excluded_statuses = [
            ProjectStatus.PLANNING
        ]

        if user.has_role(Role.MANAGER):
            return queryset.filter(
                manager=user,
                is_hidden=False
            ).exclude(status__in=excluded_statuses).distinct()

        if user.has_role(Role.EMPLOYEE):
            return queryset.filter(
                Q(testers=user) | Q(employees=user),
                is_hidden=False
            ).exclude(status__in=excluded_statuses).distinct()

        return queryset.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.created_by != user:
            raise PermissionDenied(
                "Sizda bu loyihani o'chirish huquqi yo'q. Faqat loyihani yaratuvchisi uni o'chira oladi.")

        if instance.status != ProjectStatus.PLANNING:
            raise ValidationError({
                "detail": f"Loyihani '{instance.get_status_display()}' holatida o'chirib bo'lmaydi. Faqat 'Rejalashtirilmoqda' holatidagilarni o'chirish mumkin."
            })

        instance.is_active = False
        instance.is_deleted = True
        instance.save()


@extend_schema(tags=['Tasks'])
class TaskViewSet(RoleBasedQuerySetMixin, TrashMixin, viewsets.ModelViewSet):
    queryset = Task.objects.select_related('project', 'assignee').prefetch_related('attachments')
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    full_access_roles = [Role.ADMIN, Role.AUDITOR]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]

    filterset_class = TaskFilter
    search_fields = ['assignee__username', 'uid', 'title', 'description']
    ordering_fields = ['deadline', 'priority', 'status', 'created_at']

    def get_serializer_class(self):
        if self.action == 'change_status':
            return TaskStatusUpdateSerializer
        return TaskSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'restore', 'hard_delete']:
            return [(IsAdmin | IsManager | IsEmployee)()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'action', None) in ['trash', 'restore', 'hard_delete']:
            return queryset.filter(is_deleted=True)
        return queryset.filter(is_deleted=False, is_active=True)

    def get_role_based_queryset(self, queryset, user):
        active_projects_filter = Q(project__is_hidden=False) & ~Q(project__status=ProjectStatus.PLANNING)

        if user.has_role(Role.MANAGER):
            return queryset.filter(
                active_projects_filter,
                project__manager=user
            ).exclude(assignee=user)

        if user.has_role(Role.EMPLOYEE):
            return queryset.filter(
                active_projects_filter,
                Q(assignee=user) |
                Q(project__testers=user, status__in=[TaskStatus.PRODUCTION, TaskStatus.CHECKED]) |
                Q(project__employees=user, assignee__isnull=True)
            ).distinct()

        return queryset.none()

    def perform_create(self, serializer):
        task = TaskService.create_task(self.request.user, serializer.validated_data)
        serializer.instance = task

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.created_by != user:
            raise PermissionDenied(
                "Sizda bu vazifani o'chirish huquqi yo'q. Faqat vazifa yaratuvchisi uni o'chira oladi.")

        if instance.status != TaskStatus.TODO:
            raise ValidationError({
                "detail": f"Vazifani '{instance.get_status_display()}' holatida o'chirib bo'lmaydi. Faqat 'Qilinishi kerak' holatidagilarni o'chirish mumkin."
            })

        instance.is_active = False
        instance.is_deleted = True
        instance.save()

    def perform_update(self, serializer):
        user = self.request.user
        task = self.get_object()

        if task.status != TaskStatus.TODO:
            raise PermissionDenied(
                "Vazifa jarayonga tushgan yoki yakunlangan. Uni endi tahrirlab bo'lmaydi."
            )

        is_admin_or_manager = user.is_superuser or user.has_role(Role.ADMIN) or task.project.manager == user
        is_creator = task.created_by == user

        if is_admin_or_manager or is_creator:
            serializer.save()
        else:
            raise PermissionDenied("Sizda ushbu vazifani tahrirlash huquqi yo'q.")

    @extend_schema(
        tags=['Tasks'],
        request=TaskStatusUpdateSerializer,
        responses={200: TaskSerializer}
    )
    @action(detail=True, methods=['patch'], url_path='change-status')
    def change_status(self, request, pk=None):
        task = self.get_object()

        serializer = self.get_serializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data.get('status')
        rejection_reason = serializer.validated_data.get('rejection_reason')
        updated_task = TaskService.change_status(task, request.user, new_status, rejection_reason)

        return Response(TaskSerializer(updated_task).data)


@extend_schema(tags=['Task Attachments'])
class TaskAttachmentViewSet(SoftDeleteMixin, RoleBasedQuerySetMixin, viewsets.ModelViewSet):
    queryset = TaskAttachment.objects.filter(is_active=True).select_related('task__project', 'task__assignee')
    serializer_class = TaskAttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['task']
    http_method_names = ['get', 'post', 'delete']

    full_access_roles = [Role.ADMIN, Role.AUDITOR]

    def get_role_based_queryset(self, queryset, user):
        active_project_q = Q(
            task__project__is_hidden=False,
            task__project__is_active=True
        ) & ~Q(task__project__status=ProjectStatus.PLANNING)

        if user.has_role(Role.MANAGER):
            return queryset.filter(
                active_project_q,
                task__project__manager=user
            ).distinct()

        if user.has_role(Role.EMPLOYEE):
            return queryset.filter(
                active_project_q,
                Q(task__assignee=user) | Q(task__project__testers=user)
            ).distinct()

        return queryset.none()

    def perform_create(self, serializer):
        task = serializer.validated_data.get('task')

        locked_statuses = [
            TaskStatus.DONE,
            TaskStatus.CHECKED,
            TaskStatus.PRODUCTION
        ]

        if task.status in locked_statuses:
            raise ValidationError(
                f"Vazifa '{task.get_status_display()}' holatida bo'lgani uchun unga fayl biriktira olmaysiz."
            )

        serializer.save()


@extend_schema(tags=['Task Rejections'])
class TaskRejectionFileViewSet(viewsets.ModelViewSet):
    queryset = TaskRejectionFile.objects.select_related('task__project')
    serializer_class = TaskRejectionFileSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['task']
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()

        if user.is_superuser or user.has_any_role(Role.ADMIN, Role.AUDITOR):
            return queryset

        active_project_filter = Q(
            task__project__is_hidden=False,
            task__project__is_active=True
        ) & ~Q(task__project__status=ProjectStatus.PLANNING)

        if user.has_role(Role.MANAGER):
            return queryset.filter(
                active_project_filter,
                task__project__manager=user
            ).distinct()

        if user.has_role(Role.EMPLOYEE):
            return queryset.filter(
                active_project_filter,
                Q(task__assignee=user) | Q(task__project__testers=user)
            ).distinct()

        return queryset.none()

    def perform_create(self, serializer):
        task = serializer.validated_data.get('task')
        user = self.request.user

        allowed_statuses = [TaskStatus.PRODUCTION, TaskStatus.IN_PROGRESS]

        if task.status not in allowed_statuses:
            raise ValidationError("Vazifa bu holatda bo'lganda fayl yuklab bo'lmaydi.")

        is_tester = user in task.project.testers.all()
        is_manager = task.project.manager == user
        is_admin = user.is_superuser or user.has_role(Role.ADMIN)

        if is_tester and not (is_admin or is_manager):
            if task.position_id and user.position_id != task.position_id:
                raise PermissionDenied("Siz faqat o'z lavozimingizga mos vazifalarga rasm yuklay olasiz.")

        if not (is_admin or is_tester or is_manager):
            raise PermissionDenied("Sizda bu vazifaga rasm yuklash huquqi yo'q.")

        serializer.save()


@extend_schema(tags=['Meetings'])
class MeetingViewSet(SoftDeleteMixin, RoleBasedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Meeting.objects.filter(is_active=True)
    serializer_class = MeetingSerializer

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = MeetingFilter
    search_fields = ['title', 'description']
    ordering_fields = ['start_time', 'created_at']

    full_access_roles = [Role.ADMIN, Role.AUDITOR]

    def get_role_based_queryset(self, queryset, user):
        active_project_filter = Q(
            project__is_hidden=False,
            project__is_active=True
        ) & ~Q(project__status=ProjectStatus.PLANNING)

        if user.has_role(Role.MANAGER):
            return queryset.filter(
                active_project_filter,
                project__manager=user
            ).distinct()

        if user.has_role(Role.EMPLOYEE):
            return queryset.filter(
                active_project_filter,
                Q(participants=user) | Q(organizer=user)
            ).distinct()

        return queryset.none()

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    @transaction.atomic
    def perform_create(self, serializer):
        meeting = MeetingService.create_meeting(self.request.user, serializer.validated_data)
        serializer.instance = meeting

    @transaction.atomic
    def perform_update(self, serializer):
        user = self.request.user
        meeting = self.get_object()
        is_privileged = user.is_superuser or user.has_role(Role.ADMIN) or \
                        meeting.project.manager == user

        if not is_privileged and meeting.organizer != user:
            raise PermissionDenied("Siz faqat o'zingiz yaratgan yig'ilishni tahrirlay olasiz.")

        participants = serializer.validated_data.pop('participants', None)
        
        time_changed = False
        if meeting._old_start_time and meeting.start_time != meeting._old_start_time:
            time_changed = True
        if meeting._old_duration_minutes and meeting.duration_minutes != meeting._old_duration_minutes:
            time_changed = True

        meeting = serializer.save()

        MeetingService.handle_participants(meeting, participants, user.id)
        
        if time_changed:
            MeetingService.notify_time_change(meeting)

    def perform_destroy(self, instance):
        user = self.request.user
        is_privileged = user.is_superuser or user.has_role(Role.ADMIN) or \
                        instance.project.manager == user

        if not is_privileged and instance.organizer != user:
            raise PermissionDenied("Siz faqat o'zingiz yaratgan yig'ilishni o'chira olasiz.")

        instance.is_active = False
        instance.is_deleted = True
        instance.save()

    @extend_schema(request=None)
    @action(detail=True, methods=['post'], url_path='close')
    def close_meeting(self, request, pk=None):
        meeting = self.get_object()
        user = self.request.user

        is_privileged = user.is_superuser or user.has_role(Role.ADMIN) or \
                        meeting.organizer == user or \
                        meeting.project.manager == user

        if not is_privileged:
            raise PermissionDenied("Faqat tashkilotchi yoki menejer yig'ilishni yopa oladi.")

        MeetingService.close_meeting(meeting)

        return Response({"message": "Yig'ilish yopildi va bildirishnomalar yuborildi."})


@extend_schema(tags=['Meeting Attendance'])
class MeetingAttendanceViewSet(SoftDeleteMixin, RoleBasedQuerySetMixin, viewsets.ModelViewSet):
    queryset = MeetingAttendance.objects.filter(is_active=True).select_related('meeting__organizer', 'user')
    serializer_class = MeetingAttendanceSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['meeting', 'user', 'is_attended']

    http_method_names = ['get', 'patch']

    full_access_roles = [Role.ADMIN, Role.AUDITOR]

    def get_role_based_queryset(self, queryset, user):
        active_project_q = Q(
            meeting__project__is_hidden=False,
            meeting__project__is_active=True
        ) & ~Q(meeting__project__status=ProjectStatus.PLANNING)

        if user.has_role(Role.MANAGER):
            return queryset.filter(
                active_project_q,
                meeting__project__manager=user
            ).distinct()

        if user.has_role(Role.EMPLOYEE):
            return queryset.filter(
                active_project_q,
                user=user
            ).distinct()

        return queryset.none()

    def perform_update(self, serializer):
        user = self.request.user
        attendance = self.get_object()

        is_privileged = user.is_superuser or user.has_role(Role.ADMIN) or \
                        attendance.meeting.organizer == user or \
                        attendance.meeting.project.manager == user

        if is_privileged:
            serializer.save()
            return

        if attendance.user == user:
            if attendance.is_attended:
                raise PermissionDenied("Qatnashgan deb belgilangan majlisga sabab yozib bo'lmaydi.")

            # Yig'ilish yopilganidan keyin 24 soat ichida sabab yozish kerak
            if attendance.meeting.is_completed and attendance.meeting.completed_at:
                from django.utils import timezone
                from datetime import timedelta
                if timezone.now() > attendance.meeting.completed_at + timedelta(hours=24):
                    raise PermissionDenied("Yig'ilish yopilganidan keyin 24 soat o'tib sabab yozib bo'lmaydi.")

            if attendance.absence_reason and 'absence_reason' in self.request.data:
                raise PermissionDenied("Siz allaqachon sabab kiritgansiz va uni o'zgartira olmaysiz.")

            serializer.save()
            return

        raise PermissionDenied("Sizda ushbu yozuvni tahrirlash uchun huquq yo'q.")
