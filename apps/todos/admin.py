from django.contrib import admin
from django.utils.safestring import mark_safe
from unfold.decorators import display
from unfold.admin import ModelAdmin, TabularInline

from .models import Todo, TodoItem


class TodoItemInline(TabularInline):
    model = TodoItem
    extra = 0


@admin.register(Todo)
class TodoAdmin(ModelAdmin):
    list_display = (
        'id',
        'user',
        'title_short',
        'color_badge',
        'deadline',
        'status_badge',
        'created_at_formatted'
    )

    list_display_links = ('id', 'user')

    list_filter = ('is_done', 'color', 'user', 'created_at')
    search_fields = ('title', 'user__username')
    ordering = ('-created_at',)
    
    inlines = [TodoItemInline]

    fieldsets = (
        ('Asosiy ma\'lumotlar', {
            'fields': ('user', 'title', 'color', 'deadline', 'is_done'),
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

    @admin.display(description="Rangi")
    def color_badge(self, obj):
        color_classes = {
            'red': 'bg-red-500',
            'green': 'bg-green-500',
            'blue': 'bg-blue-500',
            'yellow': 'bg-yellow-500',
        }
        bg_class = color_classes.get(obj.color, 'bg-gray-500')
        return mark_safe(
            f'<div class="flex items-center gap-2">'
            f'<span class="w-3 h-3 rounded-full {bg_class}"></span>'
            f'<span>{obj.get_color_display() or obj.color}</span>'
            f'</div>'
        )

    @display(
        description="Holat",
        label={
            "Bajarildi": "success",
            "Kutilmoqda": "warning"
        }
    )
    def status_badge(self, obj):
        return "Bajarildi" if obj.is_done else "Kutilmoqda"

    @admin.display(description="Yaratilgan vaqt")
    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%d.%m.%Y %H:%M")