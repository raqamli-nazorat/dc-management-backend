from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from apps.projects.models import Project, ProjectStatus
from apps.projects.serializers import ProjectShortSerializer
from apps.users.models import Role
from apps.users.serializers import UserShortSerializer, ProfileSerializer
from .models import ExpenseRequest, Ledger, Payroll, ExpenseCategory

User = get_user_model()


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ('id', 'title', 'created_at', 'updated_at')


class ExpenseCancelSerializer(serializers.Serializer):
    cancel_reason = serializers.CharField(
        required=True,
        min_length=5,
        error_messages={'required': "Bekor qilish sababini yozish shart!"}
    )


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
            'reason', 'cancel_reason', 'payment_method', 'card_number', 'status', 'accountant_info', 'paid_at',
            'confirmed_at', 'cancelled_at', 'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'status', 'paid_at', 'confirmed_at', 'cancelled_at', 'created_at', 'updated_at'
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
        user = getattr(request, 'user', None)

        if self.instance:
            instance = self.instance
            for attr, value in attrs.items():
                setattr(instance, attr, value)
        else:
            model_attrs = attrs.copy()
            if 'user' not in model_attrs and user:
                model_attrs['user'] = user
            instance = ExpenseRequest(**model_attrs)

        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            instance.clean()
        except DjangoValidationError as e:
            if hasattr(e, 'message_dict'):
                raise serializers.ValidationError(e.message_dict)
            else:
                raise serializers.ValidationError({"detail": e.messages})

        if 'project' in attrs or instance.project is None:
            attrs['project'] = instance.project

        if 'card_number' in attrs or instance.card_number is None:
            attrs['card_number'] = instance.card_number

        if 'expense_category' in attrs or instance.expense_category is None:
            attrs['expense_category'] = instance.expense_category

        return attrs


class PayrollSerializer(serializers.ModelSerializer):
    month_display = serializers.SerializerMethodField()
    user_info = ProfileSerializer(source='user', read_only=True)
    accountant_info = UserShortSerializer(source='accountant', read_only=True)

    class Meta:
        model = Payroll
        fields = (
            'id', 'user_info', 'accountant_info', 'month', 'month_display',
            'fixed_salary', 'kpi_bonus', 'penalty_amount', 'total_amount',
            'tasks_completed', 'deadline_missed', 'bug_count',
            'is_confirmed', 'confirmed_at', 'created_at'
        )

    def get_month_display(self, obj):
        return obj.month.strftime('%B, %Y')

    def validate(self, attrs):
        if self.instance:
            instance = self.instance
            for attr, value in attrs.items():
                setattr(instance, attr, value)
        else:
            instance = Payroll(**attrs)

        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            instance.clean()
        except DjangoValidationError as e:
            if hasattr(e, 'message_dict'):
                raise serializers.ValidationError(e.message_dict)
            else:
                raise serializers.ValidationError({"detail": e.messages})

        return attrs


class PayrollStatusUpdateSerializer(serializers.Serializer):
    payroll_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )


class LedgerSerializer(serializers.ModelSerializer):
    user_info = ProfileSerializer(source='user', read_only=True)

    class Meta:
        model = Ledger
        fields = ('id', 'user_info', 'amount', 'transaction_type', 'description', 'created_at',)
