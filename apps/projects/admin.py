from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from .models import (
    Project,
    Task,
    TaskAttachment,
    TaskRejectionFile,
    Meeting,
    MeetingAttendance,
    ProjectStatus,
    Type,
    ProjectDocument,
)


class ProjectDocumentInline(admin.TabularInline):
    model = ProjectDocument
    extra = 0
    fields = ("id", "name", "value", "is_active", "created_at", "updated_at")
    readonly_fields = ("id", "created_at", "updated_at")


class TaskAttachmentInline(admin.TabularInline):
    model = TaskAttachment
    extra = 0
    fields = ("id", "file", "is_active", "created_at", "updated_at")
    readonly_fields = ("id", "created_at", "updated_at")


class TaskRejectionFileInline(admin.TabularInline):
    model = TaskRejectionFile
    extra = 0
    fields = ("id", "file", "is_active", "created_at", "updated_at")
    readonly_fields = ("id", "created_at", "updated_at")


class MeetingAttendanceInline(admin.TabularInline):
    model = MeetingAttendance
    extra = 0
    fields = (
        "id",
        "user",
        "is_attended",
        "is_excused",
        "joined_at",
        "left_at",
        "duration_minutes",
        "late_minutes",
        "absence_reason",
        "payroll_processed",
        "is_active",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = (
        "id",
        "uid",
        "title",
        "prefix",
        "manager",
        "status_colored",
        "project_price",
        "penalty_percentage",
        "deadline",
        "completed_at",
        "was_overdue",
        "is_hidden",
        "is_deleted",
        "is_active",
        "created_at",
    )
    list_display_links = ("id", "uid", "title")
    list_filter = (
        "status",
        "is_active",
        "is_deleted",
        "is_hidden",
        "was_overdue",
        "payroll_processed",
        "created_at",
        "deadline",
        "manager",
    )
    search_fields = (
        "id",
        "uid",
        "prefix",
        "title",
        "description",
        "manager__username",
        "manager__first_name",
        "manager__last_name",
    )
    filter_horizontal = ("employees", "testers")
    readonly_fields = ("id", "uid", "was_overdue", "hidden_at", "created_at", "updated_at")
    inlines = [ProjectDocumentInline]

    fieldsets = (
        (
            "Loyiha haqida ma'lumot",
            {
                "fields": (
                    "id",
                    "uid",
                    "prefix",
                    "title",
                    "description",
                    "status",
                )
            },
        ),
        (
            "Moliya va hisob-kitob",
            {"fields": ("project_price", "penalty_percentage", "payroll_processed")},
        ),
        ("Jamoa", {"fields": ("created_by", "manager", "employees", "testers")}),
        (
            "Vaqt jadvali",
            {"fields": ("deadline", "completed_at", "was_overdue")},
        ),
        (
            "Ko'rinish va o'chirish",
            {"fields": ("is_hidden", "hidden_at", "is_deleted", "is_active")},
        ),
        (
            "Tizim haqida ma'lumot",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Holati", ordering="status")
    def status_colored(self, obj):
        colors = {
            ProjectStatus.PLANNING: "gray",
            ProjectStatus.ACTIVE: "blue",
            ProjectStatus.COMPLETED: "green",
            ProjectStatus.CANCELLED: "red",
            ProjectStatus.OVERDUE: "orange",
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, "black"),
            obj.get_status_display(),
        )

    def save_model(self, request, obj, form, change):
        obj._current_user = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        form.instance._current_user = request.user
        super().save_related(request, form, formsets, change)


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    list_display = (
        "id",
        "uid",
        "title",
        "project",
        "assignee",
        "position",
        "sprint",
        "type_badge",
        "priority",
        "status",
        "task_price",
        "penalty_percentage",
        "deadline",
        "actual_minutes",
        "reopened_count",
        "was_overdue",
        "is_deleted",
        "is_active",
    )
    list_display_links = ("id", "uid", "title")
    list_filter = (
        "status",
        "priority",
        "type",
        "is_active",
        "is_deleted",
        "was_overdue",
        "payroll_processed",
        "project",
        "assignee",
        "position",
        "sprint",
        "deadline",
    )
    search_fields = (
        "id",
        "uid",
        "title",
        "description",
        "project__title",
        "project__prefix",
        "assignee__username",
        "assignee__first_name",
        "assignee__last_name",
    )
    readonly_fields = ("id", "uid", "was_overdue", "created_at", "updated_at")
    inlines = [TaskAttachmentInline, TaskRejectionFileInline]

    fieldsets = (
        (
            "Asosiy",
            {
                "fields": (
                    "id",
                    "uid",
                    "project",
                    "title",
                    "description",
                    "rejection_reason",
                )
            },
        ),
        (
            "Tasniflash",
            {"fields": ("status", "priority", "type", "position", "sprint")},
        ),
        (
            "Topshiriq & narxlar",
            {
                "fields": (
                    "created_by",
                    "assignee",
                    "task_price",
                    "penalty_percentage",
                    "payroll_processed",
                )
            },
        ),
        (
            "Vaqtni kuzatish & Sifat",
            {
                "fields": (
                    "deadline",
                    "started_at",
                    "completed_at",
                    "estimated_minutes",
                    "actual_minutes",
                    "reopened_count",
                    "was_overdue",
                )
            },
        ),
        (
            "Holat",
            {"fields": ("is_deleted", "is_active")},
        ),
        (
            "Tizim haqida ma'lumot",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        obj._current_user = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Turi")
    def type_badge(self, obj):
        color = (
            "red"
            if obj.type == Type.BUG
            else "green" if obj.type == Type.FEATURE else "blue"
        )
        return format_html(
            '<b style="color: {};">{}</b>', color, obj.get_type_display()
        )


@admin.register(Meeting)
class MeetingAdmin(ModelAdmin):
    list_display = (
        "id",
        "uid",
        "title",
        "project",
        "organizer",
        "start_time",
        "duration_minutes",
        "requires_approval",
        "penalty_percentage",
        "is_completed",
        "completed_at",
        "notification_sent",
        "is_deleted",
        "is_active",
    )
    list_display_links = ("id", "uid", "title")
    list_filter = (
        "is_completed",
        "requires_approval",
        "is_active",
        "is_deleted",
        "notification_sent",
        "start_time",
        "project",
        "organizer",
    )
    search_fields = (
        "id",
        "uid",
        "title",
        "description",
        "project__title",
        "organizer__username",
    )
    readonly_fields = ("id", "uid", "created_at", "updated_at")
    inlines = [MeetingAttendanceInline]

    fieldsets = (
        (
            "Asosiy",
            {
                "fields": (
                    "id",
                    "uid",
                    "project",
                    "organizer",
                    "title",
                    "description",
                    "recording_url",
                    "requires_approval",
                    "penalty_percentage",
                )
            },
        ),
        (
            "Vaqtni kuzatish & Holat",
            {
                "fields": (
                    "start_time",
                    "duration_minutes",
                    "is_completed",
                    "completed_at",
                    "notification_sent",
                    "notification_eta",
                )
            },
        ),
        (
            "Holat va tizim haqida ma'lumot",
            {
                "fields": ("is_deleted", "is_active", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(MeetingAttendance)
class MeetingAttendanceAdmin(ModelAdmin):
    list_display = (
        "id",
        "meeting",
        "user",
        "is_attended",
        "is_excused",
        "payroll_processed",
        "joined_at",
        "left_at",
        "duration_minutes",
        "late_minutes",
        "is_active",
        "created_at",
    )
    list_display_links = ("id", "meeting")
    list_filter = (
        "is_attended",
        "is_excused",
        "payroll_processed",
        "is_active",
        "meeting",
        "user",
    )
    search_fields = (
        "id",
        "meeting__title",
        "meeting__uid",
        "user__username",
        "absence_reason",
    )
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (
            "Asosiy",
            {"fields": ("id", "meeting", "user")},
        ),
        (
            "Qatnashuv holati",
            {"fields": ("is_attended", "is_excused", "absence_reason")},
        ),
        (
            "Vaqtlar",
            {
                "fields": (
                    "joined_at",
                    "left_at",
                    "duration_minutes",
                    "late_minutes",
                )
            },
        ),
        (
            "Moliya & Tizim",
            {
                "fields": (
                    "payroll_processed",
                    "is_active",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(ModelAdmin):
    list_display = ("id", "project", "name", "value", "is_active", "created_at")
    list_display_links = ("id", "name")
    list_filter = ("is_active", "created_at", "project")
    search_fields = ("id", "name", "value", "project__title", "project__prefix")
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (
            "Asosiy",
            {"fields": ("id", "project", "name", "value")},
        ),
        (
            "Tizim haqida ma'lumot",
            {"fields": ("is_active", "created_at", "updated_at")},
        ),
    )


@admin.register(TaskAttachment)
class TaskAttachmentAdmin(ModelAdmin):
    list_display = ("id", "task", "file", "is_active", "created_at")
    list_display_links = ("id", "task")
    list_filter = ("is_active", "created_at")
    search_fields = ("id", "task__title", "task__uid")
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (
            "Asosiy",
            {"fields": ("id", "task", "file")},
        ),
        (
            "Tizim haqida ma'lumot",
            {"fields": ("is_active", "created_at", "updated_at")},
        ),
    )


@admin.register(TaskRejectionFile)
class TaskRejectionFileAdmin(ModelAdmin):
    list_display = ("id", "task", "file", "is_active", "created_at")
    list_display_links = ("id", "task")
    list_filter = ("is_active", "created_at")
    search_fields = ("id", "task__title", "task__uid")
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (
            "Asosiy",
            {"fields": ("id", "task", "file")},
        ),
        (
            "Tizim haqida ma'lumot",
            {"fields": ("is_active", "created_at", "updated_at")},
        ),
    )
