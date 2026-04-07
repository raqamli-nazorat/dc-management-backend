from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import models

from apps.common.models import BaseModel
from apps.users.models import Role

User = get_user_model()


class ProjectStatus(models.TextChoices):
    PLANNING = 'planning', 'Planning'
    ACTIVE = 'active', 'Active'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'


class Status(models.TextChoices):
    TODO = 'todo', 'To Do'
    IN_PROGRESS = 'in_progress', 'In Progress'
    DONE = 'done', 'Done'
    CHECKED = 'checked', 'Checked'
    PRODUCTION = 'production', 'Production'


class Priority(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class Type(models.TextChoices):
    BUG = 'bug', 'Bug'
    EXTRA = 'extra', 'Extra'
    FEATURE = 'feature', 'Feature'
    RESEARCH = 'research', 'Research'


class Project(BaseModel):
    title = models.CharField(max_length=255)
    description = models.TextField()
    start_date = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.PLANNING,
        db_index=True
    )

    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='manager_projects',
        db_index=True
    )

    employees = models.ManyToManyField(User, related_name='employee_projects', limit_choices_to={'role': Role.EMPLOYEE})
    auditors = models.ManyToManyField(User, related_name='audited_projects', limit_choices_to={'role': Role.AUDITOR})


class Task(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    description = models.TextField()

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO, db_index=True)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.FEATURE, db_index=True)

    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks',
                                 limit_choices_to={'role': Role.EMPLOYEE}, db_index=True)

    deadline = models.DateTimeField(db_index=True)
    estimated_hours = models.FloatField(default=0.0)
    actual_hours = models.FloatField(default=0.0)
    reopened_count = models.PositiveIntegerField(default=0)

    def clean(self):
        super().clean()

        if self.assignee and self.project:
            if not self.project.employees.filter(id=self.assignee.id).exists():
                raise ValidationError({
                    'assignee': "This employee has not joined his current team!"
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class TaskAttachment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='task_files/')
