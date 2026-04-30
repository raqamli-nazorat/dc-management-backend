from django.db import transaction
from drf_spectacular.utils import extend_schema
from django_filters.rest_framework import DjangoFilterBackend

from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets, filters, permissions, parsers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status

from apps.users.models import Role
from apps.users.permissions import IsAdmin, IsManager, IsEmployee
from apps.notifications.models import Notification, NotificationType
from apps.notifications.tasks import mass_notification_sender, notify_meeting_end

from apps.common.mixins import SoftDeleteMixin, RoleBasedQuerySetMixin

from .filters import TaskFilter, ProjectFilter, MeetingFilter
from .models import Project, ProjectStatus, Task, TaskAttachment, TaskStatus, Meeting, MeetingAttendance, \
    TaskRejectionFile
from .serializers import (ProjectShortSerializer, ProjectSerializer, TaskSerializer, TaskAttachmentSerializer, \
                          TaskStatusUpdateSerializer, MeetingSerializer, MeetingAttendanceSerializer,
                          MeetingAttendanceReasonSerializer, TaskRejectionImageSerializer)


@extend_schema(tags=['Project Shorts'])
class ProjectShortViewSet(RoleBasedQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Project.objects.filter(is_deleted=False, is_active=True).select_related('manager').prefetch_related(
        'employees', 'testers')
    serializer_class = ProjectShortSerializer
    permission_classes = [permissions.IsAuthenticated]
    full_access_roles = [Role.SUPERADMIN, Role.ADMIN, Role.AUDITOR]

    def get_role_based_queryset(self, queryset, user):
        if user.has_role(Role.MANAGER):
            return queryset.filter(manager=user).exclude(
                status__in=[ProjectStatus.COMPLETED, ProjectStatus.CANCELLED]
            ).distinct()

        return queryset.filter(
            Q(testers=user) | Q(employees=user)
        ).exclude(
            status__in=[ProjectStatus.COMPLETED, ProjectStatus.CANCELLED]
        ).distinct()


@extend_schema(tags=['Projects'])
class ProjectViewSet(RoleBasedQuerySetMixin, viewsets.ModelViewSet):
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
    full_access_roles = [Role.SUPERADMIN, Role.ADMIN, Role.AUDITOR]

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
        if user.has_role(Role.MANAGER):
            return queryset.filter(manager=user)

        return queryset.filter(
            Q(testers=user) | Q(employees=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.status != ProjectStatus.PLANNING:
            raise ValidationError({
                "detail": f"Loyihani '{instance.get_status_display()}' holatida o'chirib bo'lmaydi. Faqat 'Rejalashtirilmoqda' holatidagilarni o'chirish mumkin."
            })

        instance.is_active = False
        instance.is_deleted = True
        instance.save()

    @action(detail=False, methods=['get'])
    def trash(self, request):
        queryset = self.filter_queryset(self.get_queryset()).filter(created_by=request.user)
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(request=None)
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        instance = self.get_queryset().filter(pk=pk, created_by=request.user).first()

        if not instance:
            return Response(status=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(self.request, instance)

        if not instance.is_deleted:
            return Response({"detail": "Loyiha korzinkada emas."}, status=status.HTTP_400_BAD_REQUEST)

        instance.is_active = True
        instance.is_deleted = False
        instance.save()

        return Response({"detail": "Loyiha muvaffaqiyatli tiklandi."})

    @action(detail=True, methods=['delete'])
    def hard_delete(self, request, pk=None):
        instance = self.get_queryset().filter(pk=pk, created_by=request.user).first()

        if not instance:
            return Response(status=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(self.request, instance)

        if not instance.is_deleted:
            return Response({"detail": "Faqat korzinkadagi narsalarni butunlay o'chirish mumkin."},
                            status=status.HTTP_400_BAD_REQUEST)

        instance.is_deleted = False
        instance.is_active = False
        instance.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=['Tasks'])
class TaskViewSet(RoleBasedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Task.objects.select_related('project', 'assignee').prefetch_related('attachments')
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    full_access_roles = [Role.SUPERADMIN, Role.ADMIN, Role.AUDITOR]

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
        if user.has_role(Role.MANAGER):
            return queryset.filter(project__manager=user).exclude(assignee=user)

        return queryset.filter(
            Q(assignee=user) |
            Q(project__testers=user, status__in=[TaskStatus.PRODUCTION, TaskStatus.CHECKED]) |
            Q(project__employees=user, assignee__isnull=True)
        ).distinct()

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

    @extend_schema(
        tags=['Tasks'],
        request=TaskRejectionImageSerializer
    )
    @action(
        detail=True,
        methods=['post'],
        url_path='upload-rejection-image',
        parser_classes=[MultiPartParser, FormParser]
    )
    def upload_rejection_image(self, request, pk=None):
        task = self.get_object()

        if task.status != TaskStatus.REJECTED:
            raise PermissionDenied("Faqat rad etilgan vazifalarga rasm yuklash mumkin.")

        user = request.user
        if not (user.has_role(Role.SUPERADMIN,
                              Role.ADMIN) or user in task.project.testers.all() or task.project.manager == user):
            raise PermissionDenied("Sizda bu vazifaga rasm yuklash huquqi yo'q.")

        serializer = TaskRejectionImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = serializer.validated_data['rejection_image']

        TaskRejectionFile.objects.create(task=task, file=image)
        return Response({"message": "Rad etish rasmi muvaffaqiyatli yuklandi."})

    @extend_schema(request=None)
    @action(detail=False, methods=['get'])
    def trash(self, request):
        queryset = self.filter_queryset(self.get_queryset()).filter(created_by=request.user)
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(request=None)
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        instance = self.get_queryset().filter(pk=pk, created_by=request.user).first()

        if not instance:
            return Response(status=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(self.request, instance)

        if not instance.is_deleted:
            return Response({"detail": "Vazifa korzinkada emas."}, status=status.HTTP_400_BAD_REQUEST)

        instance.is_active = True
        instance.is_deleted = False
        instance.save()

        return Response({"detail": "Vazifa muvaffaqiyatli tiklandi."})

    @action(detail=True, methods=['delete'])
    def hard_delete(self, request, pk=None):
        instance = self.get_queryset().filter(pk=pk, created_by=request.user).first()

        if not instance:
            return Response(status=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(self.request, instance)

        if not instance.is_deleted:
            return Response({"detail": "Faqat korzinkadagi narsalarni butunlay o'chirish mumkin."},
                            status=status.HTTP_400_BAD_REQUEST)

        instance.is_deleted = False
        instance.is_active = False
        instance.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def _send_task_notification(self, task, title, message):
        if task.assignee:
            Notification.objects.create(
                user=task.assignee,
                title=title,
                message=message,
                type=NotificationType.TASK,
                extra_data={'task_id': task.id}
            )

    def perform_update(self, serializer):
        user = self.request.user
        task = self.get_object()

        if not (user.has_role(Role.SUPERADMIN, Role.ADMIN) or task.project.manager == user):
            raise PermissionDenied("Sizda vazifaning umumiy ma'lumotlarini tahrirlash huquqi yo'q.")

        serializer.save()

    @extend_schema(
        tags=['Tasks'],
        request=TaskStatusUpdateSerializer,
        responses={200: TaskSerializer}
    )
    @action(detail=True, methods=['patch'], url_path='change-status')
    def change_status(self, request, pk=None):
        user = request.user
        task = self.get_object()
        current_status = task.status

        serializer = self.get_serializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data.get('status')

        if not new_status or current_status == new_status:
            return Response(TaskSerializer(task).data)

        if user.has_role(Role.SUPERADMIN, Role.ADMIN) or task.project.manager == user:
            serializer.save()
            if new_status == TaskStatus.REJECTED:
                self._send_task_notification(task, "Vazifangiz rad etildi",
                                             f"'{task.title}' vazifasi rad etildi. Sababi: {task.rejection_reason or 'Izohsiz'}")
            elif new_status == TaskStatus.CHECKED:
                self._send_task_notification(task, "Vazifangiz tasdiqlandi",
                                             f"'{task.title}' vazifasi menejer tomonidan muvaffaqiyatli tekshirildi.")
            return Response(TaskSerializer(task).data)

        if task.assignee == user:
            employee_transitions = {
                TaskStatus.TODO: [TaskStatus.IN_PROGRESS],
                TaskStatus.IN_PROGRESS: [TaskStatus.DONE],
                TaskStatus.DONE: [TaskStatus.PRODUCTION],
                TaskStatus.REJECTED: [TaskStatus.IN_PROGRESS],
            }
            if new_status not in employee_transitions.get(current_status, []):
                raise PermissionDenied(f"'{current_status}' dan '{new_status}' ga o'tib bo'lmaydi.")

            serializer.save()
            return Response(TaskSerializer(task).data)

        if task.assignee is None and task.project.employees.filter(id=user.id).exists():
            if new_status == TaskStatus.IN_PROGRESS:
                serializer.save(
                    assignee=user,
                    position=getattr(user, 'position', None)
                )
                return Response(TaskSerializer(task).data)
            raise PermissionDenied("Vazifani olish uchun uni 'Jarayonda' holatiga o'tkazishingiz kerak.")

        is_tester = task.project.testers.filter(id=user.id).exists()
        if is_tester:
            if current_status != TaskStatus.PRODUCTION:
                raise PermissionDenied("Faqat 'Production'dagi vazifalarni tekshira olasiz.")

            if new_status not in [TaskStatus.CHECKED, TaskStatus.REJECTED]:
                raise PermissionDenied("Faqat 'Checked' yoki 'Rejected' qila olasiz.")

            serializer.save()

            if new_status == TaskStatus.REJECTED:
                self._send_task_notification(task, "Vazifangiz rad etildi",
                                             f"'{task.title}' vazifasi tester tomonidan rad etildi. Sababi: {task.rejection_reason or 'Izohsiz'}")
            elif new_status == TaskStatus.CHECKED:
                self._send_task_notification(task, "Vazifangiz tasdiqlandi",
                                             f"'{task.title}' vazifasi tester tomonidan muvaffaqiyatli tekshirildi.")
            return Response(TaskSerializer(task).data)

        raise PermissionDenied("Sizda vazifa holatini o'zgartirish huquqi yo'q.")

    def perform_create(self, serializer):
        task = serializer.save(created_by=self.request.user)

        if task.assignee:
            deadline_str = task.deadline.strftime('%d.%m.%Y %H:%M')

            title = "Yangi vazifa biriktirildi"
            message = f"Sizga '{task.title}' nomli yangi vazifa topshirildi. Deadline: {deadline_str}"

            self._send_task_notification(task, title, message)


@extend_schema(tags=['Task Attachments'])
class TaskAttachmentViewSet(SoftDeleteMixin, RoleBasedQuerySetMixin, viewsets.ModelViewSet):
    queryset = TaskAttachment.objects.filter(is_active=True).select_related('task__project', 'task__assignee')
    serializer_class = TaskAttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    http_method_names = ['get', 'post', 'delete']
    full_access_roles = [Role.SUPERADMIN, Role.ADMIN, Role.AUDITOR]

    def get_role_based_queryset(self, queryset, user):
        if user.has_role(Role.MANAGER):
            return queryset.filter(task__project__manager=user)

        return queryset.filter(
            Q(task__assignee=user) |
            Q(task__project__testers=user)
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
class MeetingViewSet(SoftDeleteMixin, RoleBasedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Meeting.objects.filter(is_active=True)
    serializer_class = MeetingSerializer

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = MeetingFilter
    search_fields = ['title', 'description']
    ordering_fields = ['start_time', 'created_at']

    full_access_roles = [Role.SUPERADMIN, Role.ADMIN, Role.AUDITOR]

    def get_role_based_queryset(self, queryset, user):
        if user.has_role(Role.MANAGER):
            return queryset.filter(project__manager=user).distinct()

        return queryset.filter(participants=user).distinct()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [(IsAdmin | IsManager)()]
        return [permissions.IsAuthenticated()]

    @transaction.atomic
    def perform_create(self, serializer):
        participants = serializer.validated_data.pop('participants', [])
        meeting = serializer.save(organizer=self.request.user)
        self._handle_participants(meeting, participants)

        if meeting.duration_minutes > 0:
            transaction.on_commit(lambda: notify_meeting_end.apply_async(
                args=[meeting.id],
                eta=meeting.start_time + timezone.timedelta(minutes=meeting.duration_minutes)
            ))

    @transaction.atomic
    def perform_update(self, serializer):
        participants = serializer.validated_data.pop('participants', None)
        meeting = serializer.save()
        self._handle_participants(meeting, participants)

    def _handle_participants(self, meeting, participants):
        if participants is None:
            return

        current_attendee_ids = set(MeetingAttendance.objects.filter(meeting=meeting).values_list('user_id', flat=True))
        new_participant_ids = {p.id for p in participants}

        MeetingAttendance.objects.filter(meeting=meeting).exclude(user_id__in=new_participant_ids).delete()

        to_add_ids = new_participant_ids - current_attendee_ids
        to_add = [p for p in participants if p.id in to_add_ids]

        if to_add:
            attendances = [
                MeetingAttendance(user=user, meeting=meeting)
                for user in to_add
            ]
            MeetingAttendance.objects.bulk_create(attendances)

            notifications_to_bulk = []
            broadcast_data = []
            start_time_str = meeting.start_time.strftime('%d.%m %H:%M')

            for member in to_add:
                if member.id != self.request.user.id:
                    msg = f"'{meeting.title}' mavzusida yig'ilish tayinlandi. Vaqti: {start_time_str}. Davomiyligi: {meeting.duration_minutes} daqiqa."

                    notifications_to_bulk.append(Notification(
                        user=member,
                        title="Yangi uchrashuv belgilandi",
                        message=msg,
                        type=NotificationType.MEETING
                    ))

                    broadcast_data.append({
                        "user_id": member.id,
                        "title": "Yangi uchrashuv belgilandi",
                        "message": msg,
                        "type": "meeting",
                        "extra_data": {
                            "meeting_id": meeting.id,
                            "action": "open_meeting",
                            "project_id": meeting.project_id
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
class MeetingAttendanceViewSet(SoftDeleteMixin, RoleBasedQuerySetMixin, viewsets.ModelViewSet):
    queryset = MeetingAttendance.objects.filter(is_active=True)
    serializer_class = MeetingAttendanceSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['meeting', 'user', 'is_attended']

    full_access_roles = [Role.SUPERADMIN, Role.ADMIN, Role.AUDITOR]

    def get_role_based_queryset(self, queryset, user):
        if user.has_role(Role.MANAGER):
            return queryset.filter(meeting__project__manager=user).exclude(user=user)

        return queryset.filter(user=user)

    def get_permissions(self):
        if self.action in ['update', 'partial_update']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

    def perform_update(self, serializer):
        user = self.request.user
        attendance = self.get_object()

        if user.has_role(Role.SUPERADMIN, Role.ADMIN, Role.MANAGER):
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
    queryset = MeetingAttendance.objects.all()
    serializer_class = MeetingAttendanceReasonSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['patch']

    def get_queryset(self):
        return MeetingAttendance.objects.filter(
            user=self.request.user,
            is_attended=False
        )
