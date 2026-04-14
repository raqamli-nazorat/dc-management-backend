from django.contrib import admin
from django.utils.html import format_html

from unfold.admin import ModelAdmin

from .models import Application, ApplicationStatus, Direction, Region


@admin.register(Region)
class RegionAdmin(ModelAdmin):
    list_display = ('id', 'name', 'created_at')
    search_fields = ('name',)


@admin.register(Direction)
class DirectionAdmin(ModelAdmin):
    list_display = ('id', 'name', 'created_at')
    search_fields = ('name',)


@admin.register(Application)
class ApplicationAdmin(ModelAdmin):
    list_display = (
        'id', 'full_name', 'phone', 'direction', 'region',
        'status_colored', 'created_at'
    )
    list_display_links = ('id', 'full_name')
    list_filter = ('status', 'direction', 'region', 'is_student')
    search_fields = ('full_name', 'phone', 'telegram')
    readonly_fields = ('reviewed_by', 'reviewed_at', 'created_at')

    fieldsets = (
        ("Shaxsiy ma'lumotlar", {
            'fields': ('full_name', 'birth_date', 'phone', 'telegram')
        }),
        ("Ta'lim", {
            'fields': ('is_student', 'university')
        }),
        ("Yo'nalish va mintaqa", {
            'fields': ('direction', 'region')
        }),
        ("Qo'shimcha", {
            'fields': ('resume', 'portfolio', 'extra_info')
        }),
        ("Ariza holati", {
            'fields': ('status', 'conclusion', 'reviewed_by', 'reviewed_at')
        }),
    )

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Holati', ordering='status')
    def status_colored(self, obj):
        colors = {
            ApplicationStatus.PENDING: ('#f59e0b', 'Kutilmoqda'),
            ApplicationStatus.ACCEPTED: ('#10b981', 'Qabul qilindi'),
            ApplicationStatus.REJECTED: ('#ef4444', 'Rad etildi'),
        }
        color, label = colors.get(obj.status, ('#6b7280', obj.status))
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, label
        )