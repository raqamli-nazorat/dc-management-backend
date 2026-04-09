from django.contrib import admin
from django.utils.html import format_html
from .models import ExpenseCategory, ExpenseRequest, Ledger, Payroll, Status, TransactionType

from unfold.admin import ModelAdmin


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(ModelAdmin):
    list_display = ('id', 'title', 'is_active')
    list_display_links = ('id', 'title')
    list_filter = ('is_active',)
    search_fields = ('title',)
    ordering = ('title',)


@admin.register(ExpenseRequest)
class ExpenseRequestAdmin(ModelAdmin):
    list_display = ('id', 'user', 'type', 'amount_formatted', 'status_colored', 'payment_method', 'created_at')
    list_display_links = ('id', 'user')

    list_filter = ('status', 'type', 'payment_method', 'created_at')
    search_fields = ('user__username', 'reason', 'card_number')

    readonly_fields = ('paid_at', 'confirmed_at', 'created_at', 'updated_at')

    fieldsets = (
        ('Asosiy ma\'lumotlar', {
            'fields': ('user', 'type', 'expense_category', 'amount', 'reason')
        }),
        ('To\'lov tafsilotlari', {
            'fields': ('payment_method', 'card_number', 'accountant')
        }),
        ('Holat va vaqtlar', {
            'fields': ('status', 'paid_at', 'confirmed_at')
        }),
        ('Tizim haqida ma\'lumot', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Miqdor', ordering='amount')
    def amount_formatted(self, obj):
        return f"{obj.amount:,.2f}"

    @admin.display(description='Holati', ordering='status')
    def status_colored(self, obj):
        colors = {
            Status.PENDING: 'orange',
            Status.PAID: 'blue',
            Status.CONFIRMED: 'green'
        }
        color = colors.get(obj.status, 'black')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())


@admin.register(Ledger)
class LedgerAdmin(ModelAdmin):
    list_display = ('id', 'user', 'transaction_type_colored', 'amount_formatted', 'expense', 'payroll', 'created_at')
    list_display_links = ('id', 'user')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('user__username', 'description')

    readonly_fields = ('user', 'expense', 'payroll', 'amount', 'transaction_type', 'description', 'created_at',
                       'updated_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Miqdori', ordering='amount')
    def amount_formatted(self, obj):
        return f"{obj.amount:,.2f}"

    @admin.display(description='Type', ordering='transaction_type')
    def transaction_type_colored(self, obj):
        color = 'green' if obj.transaction_type == TransactionType.CREDIT else 'red'
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color,
                           obj.get_transaction_type_display())


@admin.register(Payroll)
class PayrollAdmin(ModelAdmin):
    list_display = ('id', 'user', 'month', 'fixed_salary', 'total_amount_formatted', 'created_at')
    list_display_links = ('id', 'user')
    list_filter = ('month', 'created_at')
    search_fields = ('user__username',)

    readonly_fields = ('total_amount', 'created_at', 'updated_at')

    fieldsets = (
        ('Employee Info', {
            'fields': ('user', 'month')
        }),
        ('Salary Breakdown', {
            'fields': ('fixed_salary', 'kpi_bonus', 'penalty_amount', 'total_amount')
        }),
        ('Performance Metrics', {
            'fields': ('tasks_completed', 'deadline_missed', 'bug_count')
        }),
        ('System Info', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Jami miqdori', ordering='total_amount')
    def total_amount_formatted(self, obj):
        return f"{obj.total_amount:,.2f}"
