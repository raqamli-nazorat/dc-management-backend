from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.serializers import ProfileSerializer
from .models import Project, Task, TaskAttachment

User = get_user_model()


class ProjectSerializer(serializers.ModelSerializer):
    manager_info = ProfileSerializer(source='manager', read_only=True)
    employees_info = ProfileSerializer(source='employees', many=True, read_only=True)
    auditors_info = ProfileSerializer(source='auditors', many=True, read_only=True)

    manager = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True)
    auditors = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, write_only=True)
    employees = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, write_only=True)

    class Meta:
        model = Project
        fields = (
            'id', 'title', 'description', 'manager', 'manager_info',
            'auditors', 'auditors_info', 'employees', 'employees_info',
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
    assignee_info = ProfileSerializer(source='assignee', read_only=True)

    assignee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), write_only=True, required=False, allow_null=True
    )
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True)
    project_info = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Task
        fields = ('id', 'project', 'project_info', 'title', 'description', 'status', 'priority', 'type', 'assignee',
                  'assignee_info', 'deadline', 'estimated_hours', 'actual_hours',
                  'reopened_count', 'attachments', 'created_at',
                  'updated_at', 'is_active')
        read_only_fields = ('id', 'created_at', 'updated_at')

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
                    'assignee': "This employee is not assigned to this project team!"
                })

        return attrs


class TaskStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ('status',)