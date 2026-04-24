from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from apps.projects.models import Project, ProjectStatus
from apps.projects.serializers import ProjectShortSerializer
from apps.users.models import Role
from apps.users.serializers import UserShortSerializer
from .models import ExpenseRequest, Ledger, Payroll, ExpenseCategory

User = get_user_model()


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ('id', 'title', 'created_at', 'updated_at')


class ExpenseRequestSerializer(serializers.ModelSerializer):
    user_info = UserShortSerializer(source='user', read_only=True)
    accountant_info = UserShortSerializer(source='accountant', read_only=True)
    expense_category_info = ExpenseCategorySerializer(source='expense_category', read_only=True)

    expense_category = serializers.PrimaryKeyRelatedField(queryset=ExpenseCategory.objects.all(), required=False,
                                                          allow_null=True, write_only=True)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.filter(is_active=True), required=False,
                                                 allow_null=True, write_only=True)
    project_info = ProjectShortSerializer(source='project', read_only=True)

    class Meta:
        model = ExpenseRequest
        fields = (
            'id', 'user_info', 'type', 'project', 'project_info', 'expense_category', 'expense_category_info', 'amount',
            'reason', 'payment_method', 'card_number', 'status', 'accountant_info', 'paid_at',
            'confirmed_at', 'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'status', 'paid_at', 'confirmed_at', 'created_at', 'updated_at'
        )

    def __init__(self, *args, **kwargs):
        super(ExpenseRequestSerializer, self).__init__(*args, **kwargs)
        request = self.context.get('request')

        if request and hasattr(request, 'user') and request.user.is_authenticated:
            user = request.user

            queryset = Project.objects.filter(is_active=True).exclude(
                status__in=[ProjectStatus.COMPLETED, ProjectStatus.CANCELLED]
            )

            privileged_roles = [Role.SUPERADMIN, Role.ADMIN, Role.ACCOUNTANT, Role.AUDITOR]

            if hasattr(user, 'roles') and not (user.is_superuser or user.has_role(*privileged_roles)):
                self.fields['project'].queryset = queryset.filter(
                    Q(manager=user) |
                    Q(employees=user) |
                    Q(testers=user)
                ).distinct()
            else:
                self.fields['project'].queryset = queryset.all()

    def validate(self, attrs):
        request = self.context.get('request')

        if not request or not request.user or not request.user.is_authenticated:
            return attrs

        user = request.user
        instance = ExpenseRequest(**attrs, user=user)

        try:
            instance.clean()
        except Exception as e:
            raise serializers.ValidationError(
                e.message_dict if hasattr(e, 'message_dict') else str(e)
            )

        return attrs


class PayrollSerializer(serializers.ModelSerializer):
    month_display = serializers.SerializerMethodField()
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True)
    user_info = UserShortSerializer(source='user', read_only=True)

    class Meta:
        model = Payroll
        fields = (
            'id', 'user', 'user_info', 'month', 'month_display',
            'fixed_salary', 'kpi_bonus', 'penalty_amount', 'total_amount',
            'tasks_completed', 'deadline_missed', 'bug_count',
            'created_at', 'is_confirmed'
        )
        read_only_fields = (
            'id', 'user', 'total_amount', 'created_at', 'is_confirmed'
        )

    def get_month_display(self, obj):
        return obj.month.strftime('%B, %Y')


class PayrollStatusUpdateSerializer(serializers.Serializer):
    payroll_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )


class LedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ledger
        fields = '__all__'
