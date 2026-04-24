from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.models import Group
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import User, Role

from unfold.admin import ModelAdmin
from .forms import UserAdminForm

from django_celery_beat.models import (
    ClockedSchedule,
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
    SolarSchedule
)

models_to_hide = [
    ClockedSchedule,
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
    SolarSchedule,
    Group
]

for model in models_to_hide:
    try:
        admin.site.unregister(model)
    except NotRegistered:
        pass


@admin.register(User)
class CustomUserAdmin(ModelAdmin):
    form = UserAdminForm

    list_display = ('id', 'username', 'role_colored', 'fixed_salary_formatted', 'balance_colored', 'is_active')
    list_display_links = ('id', 'username')
    list_filter = ('is_active',)
    search_fields = ('username',)
    ordering = ('id',)

    fieldsets = (
        ('Kirish ma\'lumotlari', {
            'fields': ('username', 'password')
        }),
        ('Shaxsiy ma\'lumotlar', {
            'fields': (
                'avatar', 'phone_number', 'region', 'district', 
                'passport_series', 'passport_image', 'social_links'
            )
        }),
        ('Lavozim va Moliya', {
            'fields': ('position', 'roles', 'fixed_salary', 'balance')
        }),
        ('Huquqlar va Status', {
            'fields': ('is_active', 'is_staff', 'is_superuser'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        ('Yangi xodim', {
            'classes': ('wide',),
            'fields': ('username', 'phone_number', 'region', 'district', 'position',
                       'passport_series', 'passport_image', 'roles',
                       'fixed_salary', 'password'),
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

    @admin.display(description='Roli')
    def role_colored(self, obj):
        if not obj.roles or len(obj.roles) == 0:
            return mark_safe('<span style="color: gray; font-style: italic;">Qo\'shilmadi</span>')

        try:
            first_role = obj.roles[0]
            colors = {
                Role.SUPERADMIN: 'red',
                Role.ADMIN: '#d35400',
                Role.MANAGER: '#2980b9',
                Role.EMPLOYEE: '#27ae60',
                Role.AUDITOR: '#8e44ad',
                Role.ACCOUNTANT: '#f39c12',
            }
            display_text = dict(Role.choices).get(first_role, first_role)
            color = colors.get(first_role, 'black')

            return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, display_text)
        except Exception:
            return "-"

    @admin.display(description='Oylik maosh', ordering='fixed_salary')
    def fixed_salary_formatted(self, obj):
        return f"{obj.fixed_salary:,.2f}"

    @admin.display(description='Balans', ordering='balance')
    def balance_colored(self, obj):
        color = 'green' if obj.balance > 0 else 'red' if obj.balance < 0 else 'gray'
        formatted_balance = f"{obj.balance:,.2f}"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>',
                           color, formatted_balance)
