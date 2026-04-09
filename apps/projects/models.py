from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import models

from apps.common.models import BaseModel
from apps.users.models import Role

User = get_user_model()


class ProjectStatus(models.TextChoices):
    PLANNING = 'planning', 'Rejalashtirilmoqda'
    ACTIVE = 'active', 'Faol'
    COMPLETED = 'completed', 'Yakunlangan'
    CANCELLED = 'cancelled', 'Bekor qilingan'


class Status(models.TextChoices):
    TODO = 'todo', 'Kutilmoqda'
    IN_PROGRESS = 'in_progress', 'Jarayonda'
    DONE = 'done', 'Bajarildi'
    CHECKED = 'checked', 'Tekshirildi'
    PRODUCTION = 'production', 'Ishga tushirildi'


class Priority(models.TextChoices):
    LOW = 'low', 'Past'
    MEDIUM = 'medium', 'Oʻrta'
    HIGH = 'high', 'Yuqori'
    CRITICAL = 'critical', 'Kritik'


class Type(models.TextChoices):
    BUG = 'bug', 'Xatolik (Bug)'
    EXTRA = 'extra', 'Qoʻshimcha'
    FEATURE = 'feature', 'Yangi funksiya'
    RESEARCH = 'research', 'Tadqiqot/Oʻrganish'


class Project(BaseModel):
    title = models.CharField(max_length=255, verbose_name="Nomi")
    description = models.TextField(verbose_name="Tavsifi")
    start_date = models.DateTimeField(auto_now_add=True, verbose_name="Boshlanish sanasi")
    deadline = models.DateTimeField(verbose_name="Muddati")
    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.PLANNING,
        db_index=True,
        verbose_name="Holati"
    )

    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='manager_projects',
        limit_choices_to={
            'role': Role.MANAGER
        },
        db_index=True,
        verbose_name="Menejer"
    )

    employees = models.ManyToManyField(User, related_name='employee_projects', limit_choices_to={'role': Role.EMPLOYEE},
                                       verbose_name="Xodimlar")
    testers = models.ManyToManyField(User, related_name='tester_projects', verbose_name="Sinovchilar")

    class Meta:
        verbose_name = "Loyiha "
        verbose_name_plural = "Loyihalar"

    def __str__(self):
        return self.title


class Task(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name='tasks', verbose_name='Loyiha')
    title = models.CharField(max_length=255, verbose_name='Nomi')
    description = models.TextField(verbose_name='Tavsifi')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO, db_index=True,
                              verbose_name='Holati')
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM, db_index=True,
                                verbose_name='Darajasi')
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.FEATURE, db_index=True,
                            verbose_name='Turi')

    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks',
                                 limit_choices_to={'role': Role.EMPLOYEE}, db_index=True, verbose_name='Topshiruvchi')

    deadline = models.DateTimeField(db_index=True, verbose_name='Muddati')
    task_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='Vazifa narxi')
    estimated_hours = models.FloatField(default=0.0, verbose_name='Taxminiy soatlar')
    actual_hours = models.FloatField(default=0.0, verbose_name="Haqiqiy ish vaqti")
    reopened_count = models.PositiveIntegerField(default=0, verbose_name='Qaytishlar soni')

    class Meta:
        verbose_name = 'Vazifa '
        verbose_name_plural = 'Vazifalar'

    def clean(self):
        super().clean()

        if self.assignee and self.project:
            if not self.project.employees.filter(id=self.assignee.id).exists():
                raise ValidationError({
                    'assignee': "Bu xodim hozirgi jamoasiga qo'shilmagan!"
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class TaskAttachment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name='attachments', verbose_name='Vazifa')
    file = models.FileField(upload_to='task_files/', verbose_name='Fayl')

    class Meta:
        verbose_name = 'Vazifa fayli '
        verbose_name_plural = 'Vazifa fayllari'

    def __str__(self):
        return self.file.name


class Meeting(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, related_name='meetings',
                                verbose_name='Loyiha')
    organizer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='organized_meetings',
                                  verbose_name="Tashkilotchi")

    title = models.CharField(max_length=255, verbose_name='Nomi')
    description = models.TextField(verbose_name='Tavfsifi')
    link = models.URLField(verbose_name='Havolasi')

    start_time = models.DateTimeField(verbose_name='Boshlanish vaqti')
    duration_minutes = models.PositiveIntegerField(verbose_name='Davomiyligi')
    is_completed = models.BooleanField(default=False, verbose_name='Tugatildimi?')

    participants = models.ManyToManyField(User, through='MeetingAttendance', related_name='meeting_participants',
                                          verbose_name='Qatnashuvchilar')

    class Meta:
        verbose_name = 'Yig\'ilish '
        verbose_name_plural = 'Yig\'lishlar'

    def __str__(self):
        return self.title


class MeetingAttendance(BaseModel):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='attendances',
                             verbose_name='Foydalanuvchi')
    meeting = models.ForeignKey(Meeting, on_delete=models.SET_NULL, null=True, related_name='attendances',
                                verbose_name='Uchrashuv')

    is_attended = models.BooleanField(default=True, verbose_name='Qatnashdimi?')
    absence_reason = models.TextField(null=True, blank=True, verbose_name='Sababi')

    class Meta:
        verbose_name = 'Yig\'ilishga qatnashish '
        verbose_name_plural = 'Yig\'ilishga qatnashishlar'
        unique_together = ('user', 'meeting')

    def __str__(self):
        return self.meeting.title
