from django.contrib import admin
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin

from .models import Todo


@admin.register(Todo)
class TodoAdmin(ModelAdmin):
    list_display = (
        'id',
        'user',
        'title_short',
        'status_badge',
        'created_at_formatted'
    )

    list_display_links = ('id', 'user')

    list_filter = ('is_done', 'user', 'created_at')
    search_fields = ('title', 'user__username')
    ordering = ('-created_at',)

    fieldsets = (
        ('Asosiy ma\'lumotlar', {
            'fields': ('user', 'title', 'is_done'),
        }),
        ('Vaqt ko\'rsatkichlari', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description="Eslatma matni")
    def title_short(self, obj):
        return obj.title[:50] + "..." if len(obj.title) > 50 else obj.title

    @admin.display(description="Holat")
    def status_badge(self, obj):
        if obj.is_done:
            return mark_safe(
                '<span class="font-bold text-green-600 dark:text-green-400">'
                'Bajarildi</span>'
            )
        return mark_safe(
            '<span class="font-bold text-yellow-600 dark:text-yellow-400">'
            'Kutilmoqda</span>'
        )

    @admin.display(description="Yaratilgan vaqt")
    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%d.%m.%Y %H:%M")
