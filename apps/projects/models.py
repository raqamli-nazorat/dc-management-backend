from datetime import timedelta

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator, MinLengthValidator
from django.db import models, transaction
from django.utils import timezone

from apps.common.utils import generate_unique_id
from apps.common.validators import validate_file_size, validate_file_extension
from apps.common.models import BaseModel
from apps.users.models import Role
from apps.applications.models import Position
from apps.notifications.models import Notification, NotificationType

User = get_user_model()


class ProjectStatus(models.TextChoices):
    PLANNING = 'planning', 'Rejalashtirilmoqda'
    ACTIVE = 'active', 'Faol'
    OVERDUE = 'overdue', 'Muddati o\'tgan'
    COMPLETED = 'completed', 'Yakunlangan'
    CANCELLED = 'cancelled', 'Bekor qilingan'


class TaskStatus(models.TextChoices):
    TODO = 'todo', 'Qilinishi kerak'
    IN_PROGRESS = 'in_progress', 'Jarayonda'
    OVERDUE = 'overdue', 'Muddati o\'tgan'
    DONE = 'done', 'Bajarildi'
    PRODUCTION = 'production', 'Ishga tushirildi'
    CHECKED = 'checked', 'Tekshirildi'
    REJECTED = 'rejected', 'Rad etildi'


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
    uid = models.CharField(max_length=20, unique=True, editable=False, null=True, blank=True, verbose_name="UID")
    prefix = models.CharField(max_length=10, unique=True, verbose_name="Prefiksi")
    title = models.CharField(max_length=255, verbose_name="Nomi")
    description = models.TextField(null=True, blank=True, verbose_name="Tavsifi")
    deadline = models.DateTimeField(verbose_name="Muddati")
    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.PLANNING,
        db_index=True,
        verbose_name="Holati"
    )

    project_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        verbose_name="Menejer bonusi (Loyiha uchun)"
    )

    penalty_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00,
                                             validators=[MinValueValidator(0), MaxValueValidator(100)],
                                             verbose_name='Jarima foizi (%)')

    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="O'chirilganmi?")
    is_hidden = models.BooleanField(default=False, db_index=True, verbose_name="Yashirilganmi?")

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='created_projects',
        null=True,
        blank=True,
        verbose_name="Yaratuvchi"
    )

    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='manager_projects',
        limit_choices_to={
            'roles__contains': [Role.MANAGER]
        },
        db_index=True,
        verbose_name="Menejer"
    )

    employees = models.ManyToManyField(User, related_name='employee_projects',
                                       limit_choices_to={'roles__contains': [Role.EMPLOYEE]},
                                       blank=True,
                                       verbose_name="Xodimlar")
    testers = models.ManyToManyField(User, related_name='tester_projects',
                                     limit_choices_to={'roles__overlap': [Role.EMPLOYEE]},
                                     blank=True,
                                     verbose_name="Sinovchilar")

    completed_at = models.DateTimeField(null=True, blank=True)
    payroll_processed = models.BooleanField(default=False)
    was_overdue = models.BooleanField(default=False, editable=False)
    hidden_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Loyiha "
        verbose_name_plural = "Loyihalar"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        deferred_fields = self.get_deferred_fields()

        if 'manager' not in deferred_fields:
            self._old_manager_id = self.manager_id
        else:
            self._old_manager_id = None

        if 'status' not in deferred_fields:
            self._old_status = self.status
        else:
            self._old_status = None

        if 'deadline' not in deferred_fields:
            self._old_deadline = self.deadline
        else:
            self._old_deadline = None

        if 'is_hidden' not in deferred_fields:
            self._old_is_hidden = getattr(self, 'is_hidden', None)
        else:
            self._old_is_hidden = None

    def clean(self):
        super().clean()

        if self.pk:
            try:
                old_project = Project.objects.get(pk=self.pk)
            except Project.DoesNotExist:
                return

            if old_project.status == ProjectStatus.ACTIVE:
                if old_project.manager_id != self.manager_id:
                    raise ValidationError({
                        'manager': "Loyiha faol holatida menejerni o'zgartirib bo'lmaydi!"
                    })

            old_status = old_project.status
            new_status = self.status

            if old_status != new_status:
                if old_status in [ProjectStatus.COMPLETED, ProjectStatus.CANCELLED]:
                    raise ValidationError({
                        'status': f"Loyiha {old_project.get_status_display()} holatida. Uning statusini qayta o'zgartirib bo'lmaydi!"
                    })

                valid_transitions = {
                    ProjectStatus.PLANNING: [ProjectStatus.ACTIVE, ProjectStatus.CANCELLED],
                    ProjectStatus.ACTIVE: [ProjectStatus.COMPLETED, ProjectStatus.CANCELLED],
                    ProjectStatus.OVERDUE: [ProjectStatus.COMPLETED, ProjectStatus.CANCELLED],
                }

                allowed_next_states = valid_transitions.get(old_status, [])
                if new_status not in allowed_next_states:

                    if new_status == ProjectStatus.OVERDUE:
                        raise ValidationError({
                            'status': "Muddati o'tgan holatini qo'lda belgilab bo'lmaydi! U tizim tomonidan avtomatik amalga oshiriladi."
                        })

                    raise ValidationError({
                        'status': f"Statusni {old_project.get_status_display()} dan {dict(ProjectStatus.choices).get(new_status)} ga o'tkazish mantiqqa to'g'ri kelmaydi!"
                    })

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        self.full_clean()

        if not self.uid:
            self.uid = generate_unique_id('PR', Project)

        if not is_new:
            if self.is_hidden and not self._old_is_hidden:
                self.hidden_at = timezone.now()

            elif not self.is_hidden and self._old_is_hidden and self.hidden_at:
                if self.deadline == self._old_deadline:
                    now = timezone.now()
                    working_seconds = 0
                    current_time = self.hidden_at
                    while current_time < now:
                        next_checkpoint = min(now,
                                              (current_time + timedelta(days=1)).replace(hour=0, minute=0, second=0,
                                                                                         microsecond=0))
                        if current_time.weekday() != 6:
                            working_seconds += (next_checkpoint - current_time).total_seconds()
                        current_time = next_checkpoint

                    self.deadline = self.deadline + timedelta(seconds=working_seconds)
                    self._was_unfrozen = True
                    self._unfreeze_working_seconds = working_seconds

                if self.status == ProjectStatus.OVERDUE and self.deadline > timezone.now():
                    self.status = ProjectStatus.ACTIVE
                    self.was_overdue = False

                self.hidden_at = None

            if self.deadline != self._old_deadline and self.is_hidden == self._old_is_hidden:
                if self.deadline > timezone.now() and self.status == ProjectStatus.OVERDUE:
                    self.status = ProjectStatus.ACTIVE

            if self.status != self._old_status:
                if self.status == ProjectStatus.COMPLETED:
                    self.completed_at = timezone.now()
                elif self._old_status == ProjectStatus.COMPLETED:
                    self.completed_at = None

            if self.status == ProjectStatus.OVERDUE:
                self.was_overdue = True

        return super().save(*args, **kwargs)


class ProjectDocument(BaseModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name="Loyiha"
    )
    name = models.CharField(max_length=255, verbose_name="Hujjat nomi")
    url = models.URLField(verbose_name="Hujjat havolasi")

    def __str__(self):
        return f"{self.name} ({self.project.title})"

    class Meta:
        verbose_name = "Loyiha hujjati"
        verbose_name_plural = "Loyiha hujjatlari"


class Task(BaseModel):
    uid = models.CharField(max_length=20, unique=True, editable=False, verbose_name="UID")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name='tasks', verbose_name='Loyiha')
    title = models.CharField(max_length=255, verbose_name='Nomi')
    description = models.TextField(null=True, blank=True, verbose_name='Tavsifi')

    rejection_reason = models.TextField(null=True, blank=True, verbose_name="Rad etish sababi")

    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.TODO, db_index=True,
                              verbose_name='Holati')
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM, db_index=True,
                                verbose_name='Darajasi')
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.FEATURE, db_index=True,
                            verbose_name='Turi')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_tasks', verbose_name='Yaratuvchi')
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks',
                                 limit_choices_to={'roles__contains': [Role.EMPLOYEE]}, db_index=True,
                                 verbose_name='Topshiruvchi')

    deadline = models.DateTimeField(db_index=True, verbose_name='Muddati')
    started_at = models.DateTimeField(null=True, blank=True)
    task_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='Vazifa narxi')
    penalty_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00,
                                             validators=[MinValueValidator(0), MaxValueValidator(100)],
                                             verbose_name='Jarima foizi (%)')

    sprint = models.PositiveSmallIntegerField(null=True, blank=True,
                                              validators=[MinValueValidator(1), MaxValueValidator(10)],
                                              verbose_name='Sprint')
    position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks',
                                 verbose_name='Lavozim')

    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="O'chirilganmi?")

    estimated_minutes = models.PositiveIntegerField(default=0, verbose_name='Taxminiy vaqt (daqiqa)')
    actual_minutes = models.PositiveIntegerField(default=0, verbose_name="Haqiqiy ish vaqti (daqiqa)")
    reopened_count = models.PositiveIntegerField(default=0, verbose_name='Qaytishlar soni')

    completed_at = models.DateTimeField(null=True, blank=True)
    payroll_processed = models.BooleanField(default=False)
    was_overdue = models.BooleanField(default=False, editable=False)

    class Meta:
        verbose_name = 'Vazifa '
        verbose_name_plural = 'Vazifalar'
        ordering = ['-created_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        deferred_fields = self.get_deferred_fields()

        if 'status' not in deferred_fields:
            self._old_status = self.status
        else:
            self._old_status = None

        if 'deadline' not in deferred_fields:
            self._old_deadline = self.deadline
        else:
            self._old_deadline = None

    def clean(self):
        super().clean()

        if not self.pk and self.project_id:
            p_status = self.project.status
            if p_status in [ProjectStatus.PLANNING, ProjectStatus.COMPLETED, ProjectStatus.CANCELLED]:
                raise ValidationError({
                    'project': f"Loyiha {self.project.get_status_display()} holatida. Yangi vazifa qo'shish taqiqlanadi!"
                })

        if self.assignee and self.position:
            if self.assignee.position != self.position:
                raise ValidationError({
                    'assignee': f"Ushbu vazifa {self.position} lavozimi uchun. Tanlangan xodim esa {self.assignee.position}."
                })

        if self.pk:
            try:
                old_task = Task.objects.only('project_id', 'status', 'assignee_id').get(pk=self.pk)
            except Task.DoesNotExist:
                return

            if old_task.project_id != self.project_id:
                raise ValidationError({'project': "Vazifa boshqa loyihaga ko'chirilishi mumkin emas!"})

            locked_statuses = [
                TaskStatus.IN_PROGRESS, TaskStatus.DONE,
                TaskStatus.PRODUCTION, TaskStatus.CHECKED,
                TaskStatus.REJECTED, TaskStatus.OVERDUE
            ]
            if old_task.status in locked_statuses and old_task.assignee_id != self.assignee_id:
                raise ValidationError({
                    'assignee': f"Vazifa {old_task.get_status_display()} holatida. Mas'ul xodimni o'zgartirib bo'lmaydi!"
                })

        if self.assignee and self.project_id:
            if not self.project.employees.filter(id=self.assignee_id).exists():
                raise ValidationError({'assignee': "Xodim loyiha a'zolari ro'yxatida topilmadi!"})

    def save(self, *args, **kwargs):
        self.full_clean()

        if not self.uid:
            self.uid = generate_unique_id(f"{self.project.prefix}-V-", Task)

        if not self.position and self.assignee:
            self.position = self.assignee.position

        if self.pk:

            if self.deadline != self._old_deadline:
                if self.deadline > timezone.now() and self.status == TaskStatus.OVERDUE:
                    self.status = TaskStatus.IN_PROGRESS

            if self.status != self._old_status:
                if self.status == TaskStatus.CHECKED:
                    self.completed_at = timezone.now()
                elif self._old_status == TaskStatus.CHECKED:
                    self.completed_at = None

            if self.status == TaskStatus.OVERDUE:
                self.was_overdue = True

        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class TaskAttachment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name='attachments', verbose_name='Vazifa')
    file = models.FileField(upload_to='tasks/files/', validators=[validate_file_size],
                            verbose_name='Fayl')

    class Meta:
        verbose_name = 'Vazifa fayli '
        verbose_name_plural = 'Vazifa fayllari'
        ordering = ['-created_at']

    def __str__(self):
        return self.file.name


class TaskRejectionFile(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='rejection_files', verbose_name='Vazifa')
    file = models.ImageField(upload_to='tasks/rejections/', validators=[validate_file_size],
                             verbose_name='Rasm (Skrinshot)')

    class Meta:
        verbose_name = 'Rad etish fayli '
        verbose_name_plural = 'Rad etish fayllari'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.task.title} - Rad etish rasmi"


class Meeting(BaseModel):
    uid = models.CharField(max_length=20, unique=True, editable=False, verbose_name="UID")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, related_name='meetings',
                                verbose_name='Loyiha')
    organizer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='organized_meetings',
                                  verbose_name="Tashkilotchi")

    title = models.CharField(max_length=255, verbose_name='Nomi')
    description = models.TextField(verbose_name='Tavfsifi')
    link = models.URLField(verbose_name='Havolasi')
    penalty_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00,
                                             validators=[MinValueValidator(0), MaxValueValidator(100)],
                                             verbose_name='Jarima foizi (%)')

    start_time = models.DateTimeField(verbose_name='Boshlanish vaqti')
    duration_minutes = models.PositiveIntegerField(verbose_name='Davomiyligi')
    is_completed = models.BooleanField(default=False, db_index=True, verbose_name='Tugatildimi?')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Tugallangan vaqt')
    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="O'chirilganmi?")

    participants = models.ManyToManyField(User, through='MeetingAttendance', related_name='meeting_participants',
                                          verbose_name='Qatnashuvchilar')

    class Meta:
        verbose_name = 'Yig\'ilish '
        verbose_name_plural = 'Yig\'lishlar'
        ordering = ['-created_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        deferred_fields = self.get_deferred_fields()

        if 'project' not in deferred_fields:
            self._old_project_id = self.project_id
        else:
            self._old_project_id = None

        if 'start_time' not in deferred_fields:
            self._old_start_time = self.start_time
        else:
            self._old_start_time = None

        if 'duration_minutes' not in deferred_fields:
            self._old_duration_minutes = self.duration_minutes
        else:
            self._old_duration_minutes = None

    def clean(self):
        super().clean()

        if self.pk:
            if self.project_id != self._old_project_id:
                raise ValidationError({
                    'project': "Yig'ilish loyihasini o'zgartirib bo'lmaydi!"
                })
        else:
            if self.project_id:
                p_status = self.project.status
                if p_status in [ProjectStatus.PLANNING, ProjectStatus.COMPLETED, ProjectStatus.CANCELLED]:
                    raise ValidationError({
                        'project': f"Loyiha {self.project.get_status_display()} holatida. Yangi yig'ilish qo'shish taqiqlanadi!"
                    })

    def save(self, *args, **kwargs):
        self.full_clean()

        if not self.uid:
            prefix = f"{self.project.prefix}-M-" if self.project else "MT"
            self.uid = generate_unique_id(prefix, Meeting)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class MeetingAttendance(BaseModel):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='attendances',
                             verbose_name='Foydalanuvchi')
    meeting = models.ForeignKey(Meeting, on_delete=models.SET_NULL, null=True, related_name='attendances',
                                verbose_name='Uchrashuv')

    is_attended = models.BooleanField(default=True, db_index=True, verbose_name='Qatnashdimi?')
    is_excused = models.BooleanField(default=False, db_index=True, verbose_name="Sabablimi?")
    payroll_processed = models.BooleanField(default=False, verbose_name="Oylikda hisoblandimi?")
    absence_reason = models.TextField(
        null=True, blank=True,
        validators=[MinLengthValidator(10)],
        verbose_name="Sabab"
    )

    class Meta:
        verbose_name = 'Yig\'ilishga qatnashish '
        verbose_name_plural = 'Yig\'ilishga qatnashishlar'
        unique_together = ('user', 'meeting')
        ordering = ['-created_at']

    def __str__(self):
        meeting_title = self.meeting.title if self.meeting else "Noma'lum yig'ilish"
        user_name = self.user.username if self.user else "Noma'lum foydalanuvchi"
        return f"{user_name} - {meeting_title}"
