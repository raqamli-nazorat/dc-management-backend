from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.serializers import UserShortSerializer
from apps.users.models import Role
from .models import Project, Task, TaskAttachment, Status, Meeting, MeetingAttendance

User = get_user_model()


class ProjectSerializer(serializers.ModelSerializer):
    manager_info = UserShortSerializer(source='manager', read_only=True)
    employees_info = UserShortSerializer(source='employees', many=True, read_only=True)
    testers_info = UserShortSerializer(source='testers', many=True, read_only=True)

    manager = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True)
    testers = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, write_only=True)
    employees = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, write_only=True)

    class Meta:
        model = Project
        fields = (
            'id', 'title', 'description', 'manager', 'manager_info',
            'testers', 'testers_info', 'employees', 'employees_info',
            'start_date', 'deadline', 'status', 'created_at', 'updated_at', 'is_active'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class TaskAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskAttachment
        fields = ('id', 'task', 'file', 'created_at', 'updated_at', 'is_active')
        read_only_fields = ('id', 'created_at', 'updated_at')


class TaskSerializer(serializers.ModelSerializer):
    attachments = TaskAttachmentSerializer(many=True, read_only=True)
    assignee_info = UserShortSerializer(source='assignee', read_only=True)

    assignee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), write_only=True, required=False, allow_null=True
    )
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True)
    project_info = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Task
        fields = (
            'id', 'project', 'project_info', 'title', 'description', 'status', 'priority', 'type',
            'assignee', 'assignee_info', 'deadline', 'task_price', 'estimated_hours', 'actual_hours',
            'reopened_count', 'attachments', 'created_at', 'updated_at', 'is_active'
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'reopened_count')

    def validate_task_price(self, value):
        user = self.context['request'].user
        if user.role == Role.EMPLOYEE and value > 0:
            return 0.00
        return value

    def get_project_info(self, obj):
        project = obj.project
        return {
            'id': project.id,
            'title': project.title,
            'description': project.description,
            'start_date': project.start_date,
            'deadline': project.deadline,
            'status': project.status
        }

    def validate(self, attrs):
        assignee = attrs.get('assignee')
        project = attrs.get('project')

        if not project and self.instance:
            project = self.instance.project
        if not assignee and self.instance:
            assignee = self.instance.assignee

        if assignee and project:
            if not project.employees.filter(id=assignee.id).exists():
                raise serializers.ValidationError({
                    'assignee': "Bu xodim ushbu loyiha jamoasiga tayinlanmagan!"
                })

        return attrs


class TaskStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ('status',)

    def validate_status(self, value):
        task = self.instance
        if value == Status.TODO and task.status in [Status.DONE, Status.CHECKED]:
            task.reopened_count += 1
            task.save(update_fields=['reopened_count'])
        return value


class MeetingSerializer(serializers.ModelSerializer):
    participants_info = UserShortSerializer(source='participants', many=True, read_only=True)

    class Meta:
        model = Meeting
        fields = (
            'id', 'project', 'organizer', 'title', 'description',
            'link', 'start_time', 'duration_minutes', 'is_completed', 'participants_info',
        )
        read_only_fields = ('organizer', 'participants_info')


class MeetingAttendanceSerializer(serializers.ModelSerializer):
    user_info = UserShortSerializer(source='user', read_only=True)

    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True)

    class Meta:
        model = MeetingAttendance
        fields = ('id', 'user', 'user_info', 'meeting', 'is_attended', 'absence_reason')
        read_only_fields = ('user', 'meeting')

    def validate(self, attrs):
        is_attended = attrs.get('is_attended')
        absence_reason = attrs.get('absence_reason')

        if is_attended is True and absence_reason:
            attrs['absence_reason'] = None

        return attrs
