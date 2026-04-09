from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Project, Task, TaskAttachment, Meeting,
    MeetingAttendance, ProjectStatus, Type
)

from unfold.admin import ModelAdmin


class TaskAttachmentInline(admin.TabularInline):
    model = TaskAttachment
    extra = 1


class MeetingAttendanceInline(admin.TabularInline):
    model = MeetingAttendance
    extra = 0
    fields = ('user', 'is_attended', 'absence_reason')
    readonly_fields = ('user',)
    can_delete = False


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ('id', 'title', 'manager', 'status_colored', 'start_date', 'deadline')
    list_display_links = ('id', 'title')
    list_filter = ('status', 'start_date', 'deadline', 'manager')
    search_fields = ('title', 'description', 'manager__username')
    filter_horizontal = ('employees', 'testers')

    fieldsets = (
        ('Project Info', {
            'fields': ('title', 'description', 'status', 'is_active')
        }),
        ('Team', {
            'fields': ('manager', 'employees', 'testers')
        }),
        ('Timeline', {
            'fields': ('deadline',)
        }),
    )

    @admin.display(description='Holati', ordering='status')
    def status_colored(self, obj):
        colors = {
            ProjectStatus.PLANNING: 'gray',
            ProjectStatus.ACTIVE: 'blue',
            ProjectStatus.COMPLETED: 'green',
            ProjectStatus.CANCELLED: 'red',
        }
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>',
                           colors.get(obj.status, 'black'), obj.get_status_display())


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    list_display = ('id', 'title', 'project', 'assignee', 'type_badge', 'priority', 'status', 'deadline')
    list_display_links = ('id', 'title')
    list_filter = ('status', 'priority', 'type', 'project', 'assignee', 'deadline')
    search_fields = ('title', 'description', 'project__title', 'assignee__username')

    inlines = [TaskAttachmentInline]

    fieldsets = (
        ('General', {
            'fields': ('project', 'title', 'description')
        }),
        ('Categorization', {
            'fields': ('status', 'priority', 'type')
        }),
        ('Assignment & Pricing', {
            'fields': ('assignee', 'task_price')
        }),
        ('Time Tracking & Quality', {
            'fields': ('deadline', 'estimated_hours', 'actual_hours', 'reopened_count')
        }),
    )

    @admin.display(description='Turi')
    def type_badge(self, obj):
        color = 'red' if obj.type == Type.BUG else 'green' if obj.type == Type.FEATURE else 'blue'
        return format_html('<b style="color: {};">{}</b>', color, obj.get_type_display())


@admin.register(TaskAttachment)
class TaskAttachmentAdmin(ModelAdmin):
    list_display = ('id', 'task', 'file', 'created_at')
    search_fields = ('task__title', 'file')


@admin.register(Meeting)
class MeetingAdmin(ModelAdmin):
    list_display = ('id', 'title', 'project', 'organizer', 'start_time', 'is_completed')
    list_filter = ('is_completed', 'start_time', 'project', 'organizer')
    search_fields = ('title', 'description', 'project__title', 'organizer__username')

    inlines = [MeetingAttendanceInline]

    fieldsets = (
        ('Meeting Details', {
            'fields': ('project', 'organizer', 'title', 'description', 'link')
        }),
        ('Schedule', {
            'fields': ('start_time', 'duration_minutes', 'is_completed')
        }),
    )


@admin.register(MeetingAttendance)
class MeetingAttendanceAdmin(ModelAdmin):
    list_display = ('id', 'meeting', 'user', 'is_attended', 'absence_reason_excerpt')
    list_filter = ('is_attended', 'meeting', 'user')
    search_fields = ('meeting__title', 'user__username', 'absence_reason')

    @admin.display(description='Sababi')
    def absence_reason_excerpt(self, obj):
        if obj.absence_reason:
            return obj.absence_reason[:30] + '...' if len(obj.absence_reason) > 30 else obj.absence_reason
        return "-"
