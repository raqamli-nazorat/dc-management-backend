from django.contrib import admin
from .models import Notification

from unfold.admin import ModelAdmin


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ('id', 'user', 'title', 'type', 'is_read', 'created_at')
    list_display_links = ('id', 'user')
    list_filter = ('type', 'is_read', 'created_at')
    search_fields = ('user__username', 'title', 'message')
    list_editable = ('is_read',)
    autocomplete_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ("Asosiy ma'lumotlar", {
            'fields': ('user', 'title', 'message', 'type')
        }),
        ("Texnik va Holat", {
            'fields': ('extra_data', 'is_read')
        }),
        ("Vaqt", {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
