from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.applications.models import Position
from apps.applications.serializers import PositionSerializer
from apps.users.serializers import UserShortSerializer
from apps.users.models import Role

from .models import Project, Task, TaskAttachment, TaskStatus, Meeting, MeetingAttendance, TaskRejectionFile

User = get_user_model()


class ProjectShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = (
            'id', 'uid', 'prefix', 'title', 'description', 'status', 'created_at'
        )


class ProjectSerializer(serializers.ModelSerializer):
    manager_info = UserShortSerializer(source='manager', read_only=True)
    created_by_info = UserShortSerializer(source='created_by', read_only=True)
    employees_info = UserShortSerializer(source='employees', many=True, read_only=True)
    testers_info = UserShortSerializer(source='testers', many=True, read_only=True)

    manager = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, write_only=True)
    testers = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, many=True,
                                                 write_only=True)
    employees = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, many=True,
                                                   write_only=True)

    completion_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            'id', 'uid', 'prefix', 'title', 'description', 'manager', 'manager_info',
            'created_by_info', 'testers', 'testers_info',
            'project_price', 'penalty_percentage',
            'employees', 'employees_info', 'deadline', 'status', 'is_hidden',
            'created_at', 'updated_at', 'completion_percentage'
        )
        read_only_fields = ('id', 'uid', 'created_at', 'updated_at')

    def get_completion_percentage(self, obj):
        total_tasks = obj.tasks.count()
        if total_tasks == 0:
            return 0.0

        completed_statuses = [TaskStatus.DONE, TaskStatus.CHECKED, TaskStatus.PRODUCTION]
        completed_tasks = obj.tasks.filter(status__in=completed_statuses).count()

        return round((completed_tasks / total_tasks) * 100, 1)

    def validate(self, attrs):
        data = super().validate(attrs)

        m2m_fields = ['testers', 'employees']
        model_data = {k: v for k, v in data.items() if k not in m2m_fields}

        if self.instance:
            for attr, value in model_data.items():
                setattr(self.instance, attr, value)
            instance = self.instance
        else:
            instance = Project(**model_data)

        try:
            instance.clean()
        except DjangoValidationError as e:
            if hasattr(e, 'message_dict'):
                raise serializers.ValidationError(e.message_dict)
            else:
                raise serializers.ValidationError({"detail": e.messages})

        return data


class TaskAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskAttachment
        fields = ('id', 'task', 'file', 'created_at')
        read_only_fields = ('id', 'created_at')


class TaskRejectionFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskRejectionFile
        fields = ('id', 'task', 'file', 'created_at')
        read_only_fields = ('id', 'created_at')


class TaskSerializer(serializers.ModelSerializer):
    attachments = TaskAttachmentSerializer(many=True, read_only=True)
    assignee_info = UserShortSerializer(source='assignee', read_only=True)
    created_by_info = UserShortSerializer(source='created_by', read_only=True)
    position_info = PositionSerializer(source='position', read_only=True)

    rejection_files = TaskRejectionFileSerializer(many=True, read_only=True)

    position = serializers.PrimaryKeyRelatedField(queryset=Position.objects.all(), required=False, write_only=True)

    assignee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), write_only=True, required=False, allow_null=True
    )
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True)
    project_info = serializers.SerializerMethodField(read_only=True)

    estimated_input_hours = serializers.IntegerField(write_only=True, required=False, min_value=0)
    estimated_input_minutes = serializers.IntegerField(write_only=True, required=False, min_value=0, max_value=59)

    class Meta:
        model = Task
        fields = (
            'id', 'uid', 'project', 'project_info', 'title', 'description', 'status', 'priority', 'type',
            'created_by_info', 'assignee', 'assignee_info', 'deadline', 'task_price', 'penalty_percentage',

            'sprint', 'position', 'position_info',

            'estimated_minutes', 'actual_minutes',

            'estimated_input_hours', 'estimated_input_minutes',

            'reopened_count', 'rejection_reason', 'attachments', 'rejection_files',
            'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'uid', 'created_by', 'created_at', 'updated_at', 'status', 'reopened_count', 'rejection_reason',
            'estimated_minutes', 'actual_minutes'
        )

    def validate_task_price(self, value):
        user = self.context['request'].user
        if user.has_role(Role.EMPLOYEE) and value > 0:
            return 0.00
        return value

    def validate_penalty_percentage(self, value):
        user = self.context['request'].user
        if user.has_role(Role.EMPLOYEE) and value > 0:
            return 0.00
        return value

    def get_project_info(self, obj):
        project = obj.project
        return {
            'id': project.id,
            'title': project.title,
            'description': project.description,
            'status': project.status,
            'deadline': project.deadline,
            'created_at': project.created_at,
        }

    def validate(self, attrs):
        hours = attrs.pop('estimated_input_hours', None)
        minutes = attrs.pop('estimated_input_minutes', None)

        if hours is not None or minutes is not None:
            h = hours or 0
            m = minutes or 0
            attrs['estimated_minutes'] = (h * 60) + m

        if self.instance:
            instance = self.instance
            for attr, value in attrs.items():
                setattr(instance, attr, value)
        else:
            instance = Task(**attrs)

        try:
            instance.clean()
        except DjangoValidationError as e:
            if hasattr(e, 'message_dict'):
                raise serializers.ValidationError(e.message_dict)
            else:
                raise serializers.ValidationError({"detail": e.messages})

        return attrs


class TaskStatusUpdateSerializer(serializers.ModelSerializer):
    rejection_reason = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Task
        fields = ('status', 'rejection_reason')


class MeetingSerializer(serializers.ModelSerializer):
    participants_info = UserShortSerializer(source='participants', many=True, read_only=True)
    participants = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), many=True, write_only=True, required=False
    )

    class Meta:
        model = Meeting
        fields = (
            'id', 'uid', 'project', 'organizer', 'title', 'description',
            'link', 'penalty_percentage', 'start_time', 'duration_minutes', 'is_completed',
            'participants', 'participants_info',
        )
        read_only_fields = ('id', 'uid', 'organizer', 'participants_info', 'is_completed')

    def validate(self, attrs):
        instance = self.instance

        if instance:
            for attr, value in attrs.items():
                if attr != 'participants':
                    setattr(instance, attr, value)
        else:

            meeting_attrs = {k: v for k, v in attrs.items() if k != 'participants'}
            instance = Meeting(**meeting_attrs)

        try:
            instance.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict if hasattr(e, 'message_dict') else {"detail": e.messages})

        participants = attrs.get('participants')
        project = attrs.get('project') or (instance.project if instance else None)

        if project and participants:
            member_ids = set(project.employees.values_list('id', flat=True)) | \
                         set(project.testers.values_list('id', flat=True)) | \
                         {project.manager_id}

            invalid_users = [p.username for p in participants if p.id not in member_ids]

            if invalid_users:
                raise serializers.ValidationError({
                    "participants": f"Quyidagi foydalanuvchilar loyiha a'zosi emas: {', '.join(invalid_users)}"
                })

        return attrs


class MeetingAttendanceSerializer(serializers.ModelSerializer):
    user_info = UserShortSerializer(source='user', read_only=True)
    meeting_title = serializers.CharField(source='meeting.title', read_only=True)

    class Meta:
        model = MeetingAttendance
        fields = ('id', 'user_info', 'meeting', 'meeting_title', 'is_attended', 'absence_reason')
        read_only_fields = ('id', 'user_info', 'meeting')

    def validate(self, attrs):
        user = self.context['request'].user
        instance = self.instance

        if instance and instance.user == user:
            if 'is_attended' in attrs:
                raise serializers.ValidationError(
                    {"is_attended": "Siz o'z ishtirok holatingizni o'zgartira olmaysiz."}
                )

        new_is_attended = attrs.get('is_attended', instance.is_attended if instance else False)

        if new_is_attended is True:
            attrs['absence_reason'] = None

        return attrs
