from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import ExpenseRequest, Ledger, Payroll, ExpenseCategory
from ..users.serializers import UserShortSerializer

User = get_user_model()


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ('id', 'title', 'is_active', 'created_at', 'updated_at')


class ExpenseRequestSerializer(serializers.ModelSerializer):
    user_info = UserShortSerializer(source='user', read_only=True)
    accountant_info = UserShortSerializer(source='accountant', read_only=True)
    expense_category_info = ExpenseCategorySerializer(source='expense_category', read_only=True)

    expense_category = serializers.PrimaryKeyRelatedField(queryset=ExpenseCategory.objects.all(), write_only=True)

    class Meta:
        model = ExpenseRequest
        fields = (
            'id', 'user_info', 'type', 'expense_category', 'expense_category_info', 'amount', 'reason',
            'payment_method',
            'card_number', 'status', 'accountant_info', 'paid_at',
            'confirmed_at', 'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'status', 'paid_at', 'confirmed_at', 'created_at', 'updated_at'
        )

    def validate(self, attrs):
        user = self.context['request'].user
        instance = ExpenseRequest(**attrs, user=user)

        try:
            instance.clean()
        except Exception as e:
            raise serializers.ValidationError(e.message_dict if hasattr(e, 'message_dict') else str(e))

        return attrs


class PayrollSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    month_display = serializers.SerializerMethodField()

    class Meta:
        model = Payroll
        fields = (
            'id', 'user', 'user_name', 'month', 'month_display',
            'fixed_salary', 'kpi_bonus', 'penalty_amount', 'total_amount',
            'tasks_completed', 'deadline_missed', 'bug_count',
            'created_at'
        )
        read_only_fields = (
            'id', 'user', 'total_amount', 'created_at'
        )

    def get_month_display(self, obj):
        return obj.month.strftime('%B, %Y')


class LedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ledger
        fields = '__all__'
