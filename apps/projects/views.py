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
from apps.notifications.models import Notification, NotificationType
from apps.notifications.tasks import mass_notification_sender

from .models import Project, ProjectStatus, Task, TaskAttachment, TaskStatus, Meeting, MeetingAttendance
from .serializers import (ProjectShortSerializer, ProjectSerializer, TaskSerializer, TaskAttachmentSerializer, \
                          TaskStatusUpdateSerializer, MeetingSerializer, MeetingAttendanceSerializer,
                          MeetingAttendanceReasonSerializer)


@extend_schema(tags=['Projects'])
class ProjectShortViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProjectShortSerializer

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
        ).exclude(status__in=[ProjectStatus.COMPLETED, ProjectStatus.CANCELLED]).distinct()


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
        current_status = task.status

        if user.role in [Role.SUPERADMIN, Role.ADMIN] or task.project.manager == user:
            serializer.save()
            return

        if task.assignee == user:
            if new_status == TaskStatus.OVERDUE:
                raise PermissionDenied("Vazifa holatini qo'lda 'Muddati o'tgan' qilib bo'lmaydi.")

            employee_transitions = {
                TaskStatus.TODO: [TaskStatus.IN_PROGRESS],
                TaskStatus.IN_PROGRESS: [TaskStatus.TODO, TaskStatus.DONE],
                TaskStatus.DONE: [TaskStatus.TODO, TaskStatus.PRODUCTION],
                TaskStatus.REJECTED: [TaskStatus.IN_PROGRESS],
            }

            allowed_next = employee_transitions.get(current_status, [])

            if new_status not in allowed_next:
                raise PermissionDenied(
                    f"Zanjir xatosi: Siz vazifani '{current_status}' holatidan to'g'ridan-to'g'ri '{new_status}' holatiga o'tkaza olmaysiz. "
                    f"Ruxsat etilgan o'tishlar: {', '.join(allowed_next)}"
                )

            serializer.save()
            return

        is_tester = task.project.testers.filter(id=user.id).exists()
        if is_tester:
            if current_status != TaskStatus.PRODUCTION:
                raise PermissionDenied("Faqat 'Production' holatidagi vazifalarni tekshirishingiz mumkin.")

            if new_status not in [TaskStatus.CHECKED, TaskStatus.REJECTED]:
                raise PermissionDenied("Tester faqat 'Checked' yoki 'Rejected' qila oladi.")

            serializer.save()
            return

        raise PermissionDenied("Sizda ushbu vazifa holatini o'zgartirish huquqi yo'q.")


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


@extend_schema(tags=['Meetings'])
class MeetingViewSet(viewsets.ModelViewSet):
    queryset = Meeting.objects.filter(is_active=True)
    serializer_class = MeetingSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [(permissions.IsAdminUser | IsManager)()]  # Permission nomlarini tekshirib oling
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

        notifications_to_bulk = []
        broadcast_data = []
        start_time_str = meeting.start_time.strftime('%d.%m %H:%M')

        for member in project_members:
            if member.id != self.request.user.id:  # Tashkilotchining o'ziga yubormaymiz
                msg = f"'{meeting.title}' mavzusida yig'ilish tayinlandi. Vaqti: {start_time_str}"

                notifications_to_bulk.append(Notification(
                    user_id=member.id,
                    title="Yangi uchrashuv belgilandi",
                    message=msg,
                    type=NotificationType.MEETING
                ))

                broadcast_data.append({
                    "user_id": member.id,
                    "title": "Yangi uchrashuv belgilandi",
                    "message": msg,
                    "type": NotificationType.MEETING,
                    "extra_data": {
                        "meeting_id": meeting.id,
                        "action": "open_meeting",
                        "project_id": project.id
                    }
                })

        if notifications_to_bulk:
            Notification.objects.bulk_create(notifications_to_bulk)
            transaction.on_commit(lambda: mass_notification_sender.delay(broadcast_data))

    @extend_schema(request=None)
    @action(detail=True, methods=['post'], url_path='close')
    def close_meeting(self, request, pk=None):
        meeting = self.get_object()

        if meeting.is_completed:
            raise ValidationError({"detail": "Bu uchrashuv allaqachon tugagan."})

        meeting.is_completed = True
        meeting.save()

        absent_attendances = MeetingAttendance.objects.filter(meeting=meeting, is_attended=False).select_related('user')

        notifications_to_bulk = []
        broadcast_data = []

        for attendance in absent_attendances:
            msg = f"Siz '{meeting.title}' mavzusidagi uchrashuvda qatnashmadingiz. Sababini ko'rsatishingiz so'raladi."

            notifications_to_bulk.append(Notification(
                user_id=attendance.user.id,
                title="Yig'ilishda ishtirok etmadingiz.",
                message=msg,
                type=NotificationType.MEETING
            ))

            broadcast_data.append({
                "user_id": attendance.user.id,
                "title": "Yig'ilishda ishtirok etmadingiz.",
                "message": msg,
                "type": NotificationType.MEETING,
                "extra_data": {
                    "meeting_id": meeting.id,
                    "action": "open_meeting",
                    "project_id": meeting.project_id
                }
            })

        if notifications_to_bulk:
            Notification.objects.bulk_create(notifications_to_bulk)
            mass_notification_sender.delay(broadcast_data)

        return Response({"message": "Uchrashuv yopildi va bildirishnomalar yuborildi."})


@extend_schema(tags=['Meeting Attendance'])
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


@extend_schema(tags=['Meeting Attendance'])
class MeetingAttendanceReasonViewSet(viewsets.ModelViewSet):
    serializer_class = MeetingAttendanceReasonSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['patch']

    def get_queryset(self):
        return MeetingAttendance.objects.filter(
            user=self.request.user,
            is_attended=False
        )
