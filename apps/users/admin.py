from django.contrib import admin
from django.utils.html import format_html
from .models import User, Role

from unfold.admin import ModelAdmin

@admin.register(User)
class CustomUserAdmin(ModelAdmin):
    list_display = ('id', 'username', 'role_colored', 'fixed_salary_formatted', 'balance_colored', 'is_active')
    list_display_links = ('id', 'username')
    list_filter = ('role', 'is_active')
    search_fields = ('username',)
    ordering = ('id',)

    fieldsets = (
        ('Kirish ma\'lumotlari', {
            'fields': ('username', 'password')
        }),
        ('Lavozim va Moliya', {
            'fields': ('role', 'fixed_salary', 'balance')
        }),
        ('Huquqlar va Status', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        ('Yangi xodim', {
            'classes': ('wide',),
            'fields': ('username', 'password', 'role', 'fixed_salary'),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_password(obj.password)
            obj.must_change_password = True
        else:
            orig_obj = User.objects.get(pk=obj.pk)
            if obj.password != orig_obj.password:
                obj.set_password(obj.password)
                obj.must_change_password = True
        super().save_model(request, obj, form, change)

    @admin.display(description='Lavozim', ordering='role')
    def role_colored(self, obj):
        colors = {
            Role.SUPERADMIN: 'red',
            Role.ADMIN: '#d35400',
            Role.MANAGER: '#2980b9',
            Role.EMPLOYEE: '#27ae60',
        }
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>',
                           colors.get(obj.role, 'black'), obj.get_role_display())

    @admin.display(description='Oylik maosh', ordering='fixed_salary')
    def fixed_salary_formatted(self, obj):
        return f"{obj.fixed_salary:,.2f}"

    @admin.display(description='Balans', ordering='balance')
    def balance_colored(self, obj):
        color = 'green' if obj.balance > 0 else 'red' if obj.balance < 0 else 'gray'
        formatted_balance = f"{obj.balance:,.2f}"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>',
                           color, formatted_balance)