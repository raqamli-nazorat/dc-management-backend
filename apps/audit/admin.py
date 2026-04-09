import json
from django.contrib import admin
from django.utils.html import format_html
from .models import AuditLog, ActionType

from unfold.admin import ModelAdmin

@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ('id', 'timestamp_formatted', 'user', 'action_colored', 'table_name', 'record_id', 'ip_address')
    list_display_links = ('id', 'timestamp_formatted')

    list_filter = ('action', 'table_name', 'timestamp')
    search_fields = ('table_name', 'record_id', 'user__username', 'user__first_name', 'user__last_name', 'ip_address')

    readonly_fields = ('user', 'action', 'ip_address', 'table_name', 'record_id',
                       'pretty_old_values', 'pretty_new_values', 'timestamp')

    fieldsets = (
        ('Foydalanuvchi va so\'rov haqida ma\'lumot', {
            'fields': ('timestamp', 'user', 'ip_address')
        }),
        ('Harakat tafsilotlari', {
            'fields': ('action', 'table_name', 'record_id')
        }),
        ('Ma\'lumotlar o\'zgarishi', {
            'fields': ('pretty_old_values', 'pretty_new_values'),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Vaqt', ordering='timestamp')
    def timestamp_formatted(self, obj):
        return obj.timestamp.strftime("%d.%m.%Y %H:%M:%S")

    @admin.display(description='Harakat', ordering='action')
    def action_colored(self, obj):
        colors = {
            ActionType.CREATE: 'green',
            ActionType.UPDATE: 'blue',
            ActionType.DELETE: 'red',
            ActionType.CONFIRM: 'purple'
        }
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>',
                           colors.get(obj.action, 'black'), obj.get_action_display())

    @admin.display(description='Eski qiymat')
    def pretty_old_values(self, obj):
        if obj.old_values:
            formatted_json = json.dumps(obj.old_values, indent=4, ensure_ascii=False)
            return format_html('<pre style="background-color: #f8f9fa; padding: 10px; border-radius: 5px;">{}</pre>',
                               formatted_json)
        return "-"

    @admin.display(description='Yangi qiymat')
    def pretty_new_values(self, obj):
        if obj.new_values:
            formatted_json = json.dumps(obj.new_values, indent=4, ensure_ascii=False)
            return format_html('<pre style="background-color: #f8f9fa; padding: 10px; border-radius: 5px;">{}</pre>',
                               formatted_json)
        return "-"
