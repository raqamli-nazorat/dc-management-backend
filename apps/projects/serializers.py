from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.serializers import UserShortSerializer
from apps.users.models import Role

from .models import Project, Task, TaskAttachment, TaskStatus, Meeting, MeetingAttendance, TaskRejectionFile

User = get_user_model()


class ProjectShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = (
            'id', 'uid', 'title', 'description', 'status', 'created_at'
        )


class ProjectSerializer(serializers.ModelSerializer):
    manager_info = UserShortSerializer(source='manager', read_only=True)
    created_by_info = UserShortSerializer(source='created_by', read_only=True)
    employees_info = UserShortSerializer(source='employees', many=True, read_only=True)
    testers_info = UserShortSerializer(source='testers', many=True, read_only=True)

    manager = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True)
    testers = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, write_only=True)
    employees = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, write_only=True)

    completion_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            'id', 'uid', 'title', 'description', 'manager', 'manager_info',
            'created_by_info', 'testers', 'testers_info',
            'employees', 'employees_info', 'deadline', 'status',
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


class TaskAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskAttachment
        fields = ('id', 'task', 'file', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class TaskRejectionFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskRejectionFile
        fields = ('id', 'file', 'created_at')


class TaskSerializer(serializers.ModelSerializer):
    attachments = TaskAttachmentSerializer(many=True, read_only=True)
    assignee_info = UserShortSerializer(source='assignee', read_only=True)
    created_by_info = UserShortSerializer(source='created_by', read_only=True)

    rejection_files = TaskRejectionFileSerializer(many=True, read_only=True)

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

            'estimated_minutes', 'actual_minutes',

            'estimated_input_hours', 'estimated_input_minutes',

            'reopened_count', 'rejection_reason', 'attachments', 'rejection_files',
            'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'uid', 'created_by', 'created_at', 'updated_at', 'reopened_count', 'rejection_reason',
            'estimated_minutes', 'actual_minutes'
        )

    def validate_task_price(self, value):
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

        if not self.instance:
            status = attrs.get('status')
            if status and status != TaskStatus.TODO:
                raise serializers.ValidationError({
                    'status': f"Yangi vazifa faqat '{TaskStatus.TODO}' holatida yaratilishi mumkin."
                })

        hours = attrs.pop('estimated_input_hours', None)
        minutes = attrs.pop('estimated_input_minutes', None)

        if hours is not None or minutes is not None:
            h = hours or 0
            m = minutes or 0
            attrs['estimated_minutes'] = (h * 60) + m

        return attrs


class TaskRejectionImageSerializer(serializers.Serializer):
    rejection_image = serializers.ImageField(required=True)


class TaskStatusUpdateSerializer(serializers.ModelSerializer):
    rejection_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Task
        fields = (
            'status',
            'rejection_reason',
        )

    def validate(self, attrs):
        status = attrs.get('status')
        reason = attrs.get('rejection_reason')

        if status == TaskStatus.REJECTED:
            if not reason or not reason.strip():
                raise serializers.ValidationError({
                    "rejection_reason": "Vazifani rad etish uchun sabab ko'rsatish shart!"
                })
        else:
            attrs['rejection_reason'] = None

        return attrs

    def update(self, instance, validated_data):
        new_status = validated_data.get('status')
        reason = validated_data.get('rejection_reason')
        now = timezone.now()

        if new_status == TaskStatus.IN_PROGRESS and instance.status != TaskStatus.IN_PROGRESS:
            instance.started_at = now

        if new_status == TaskStatus.DONE and instance.started_at:
            elapsed = int((now - instance.started_at).total_seconds() / 60)
            instance.actual_minutes += elapsed
            instance.started_at = None

        if new_status == TaskStatus.REJECTED:
            if instance.status in [TaskStatus.DONE, TaskStatus.PRODUCTION, TaskStatus.CHECKED]:
                instance.reopened_count += 1

            instance.status = TaskStatus.IN_PROGRESS
            instance.rejection_reason = reason
            instance.started_at = now
        else:
            instance.status = new_status
            if new_status in [TaskStatus.DONE, TaskStatus.CHECKED, TaskStatus.PRODUCTION]:
                instance.rejection_reason = None

        instance.save()
        return instance


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
        read_only_fields = ('id', 'uid', 'organizer', 'participants_info', 'penalty_percentage')

    def validate(self, attrs):
        project = attrs.get('project')
        participants = attrs.get('participants', [])

        if not project and self.instance:
            project = self.instance.project

        if project and participants:
            project_member_ids = set(project.employees.values_list('id', flat=True)) | \
                                 set(project.testers.values_list('id', flat=True))

            for p in participants:
                if p.id not in project_member_ids:
                    raise serializers.ValidationError({
                        "participants": f"{p.username} ushbu loyiha a'zosi emas."
                    })

        return attrs


class MeetingAttendanceSerializer(serializers.ModelSerializer):
    user_info = UserShortSerializer(source='user', read_only=True)

    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True)

    class Meta:
        model = MeetingAttendance
        fields = ('id', 'user', 'user_info', 'meeting', 'is_attended', 'absence_reason')
        read_only_fields = ('id', 'user', 'meeting')

    def validate(self, attrs):
        is_attended = attrs.get('is_attended')
        absence_reason = attrs.get('absence_reason')

        if is_attended is True and absence_reason:
            attrs['absence_reason'] = None

        return attrs


class MeetingAttendanceReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingAttendance
        fields = ('absence_reason',)
        extra_kwargs = {
            'absence_reason': {'required': True, 'allow_blank': False}
        }
