from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, OuterRef, Subquery, IntegerField
from apps.projects.models import Project, Task, MeetingAttendance
from apps.finance.models import ExpenseRequest, Payroll

User = get_user_model()


class UserComprehensiveReportSerializer(serializers.ModelSerializer):
    report = serializers.SerializerMethodField()

    region = serializers.CharField(source='region.name', read_only=True)
    district = serializers.CharField(source='district.name', read_only=True)
    position = serializers.CharField(source='position.name', read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'phone_number',
            'region', 'district', 'position', 'roles',
            'fixed_salary', 'balance', 'report'
        )

    @staticmethod
    def setup_eager_loading(queryset):
        def get_project_subquery(status):
            return Subquery(
                Project.objects.filter(
                    Q(created_by=OuterRef('pk')) |
                    Q(manager=OuterRef('pk')) |
                    Q(employees=OuterRef('pk')) |
                    Q(testers=OuterRef('pk')),
                    status=status,
                    is_active=True,
                    is_deleted=False
                ).values('status').annotate(cnt=Count('pk', distinct=True)).values('cnt'),
                output_field=IntegerField()
            )

        def get_task_subquery(status=None, rejected=False):
            qs = Task.objects.filter(assignee=OuterRef('pk'), is_active=True, is_deleted=False)

            if status:
                qs = qs.filter(status=status)

            if rejected:
                qs = qs.filter(reopened_count__gt=0)

            return Subquery(qs.values('assignee').annotate(cnt=Count('pk')).values('cnt'), output_field=IntegerField())

        def get_meeting_subquery(attended=None, excused=None):
            qs = MeetingAttendance.objects.filter(user=OuterRef('pk'), is_active=True)

            if attended is not None:
                qs = qs.filter(is_attended=attended)

            if excused is True:
                qs = qs.filter(absence_reason__isnull=False).exclude(absence_reason='')
            elif excused is False:
                qs = qs.filter(Q(absence_reason__isnull=True) | Q(absence_reason=''))

            return Subquery(qs.values('user').annotate(cnt=Count('pk')).values('cnt'), output_field=IntegerField())

        def get_expense_subquery(status=None):
            from django.db.models import DecimalField, Sum
            qs = ExpenseRequest.objects.filter(user=OuterRef('pk'), is_active=True)

            if status:
                qs = qs.filter(status=status)

            return Subquery(qs.values('user').annotate(total=Sum('amount')).values('total'),
                            output_field=DecimalField())

        def get_payroll_subquery(field):
            from django.db.models import DecimalField, Sum

            return Subquery(
                Payroll.objects.filter(user=OuterRef('pk'), is_active=True).values('user').annotate(
                    total=Sum(field)).values('total'),
                output_field=DecimalField()
            )

        return queryset.select_related('region', 'district', 'position').annotate(
            p_comp=get_project_subquery('completed'),
            p_active=get_project_subquery('active'),
            p_canc=get_project_subquery('cancelled'),
            p_over=get_project_subquery('overdue'),
            p_plan=get_project_subquery('planning'),

            t_total=get_task_subquery(),
            t_todo=get_task_subquery(status='todo'),
            t_prog=get_task_subquery(status='in_progress'),
            t_over=get_task_subquery(status='overdue'),
            t_done=get_task_subquery(status='done'),
            t_prod=get_task_subquery(status='production'),
            t_check=get_task_subquery(status='checked'),
            t_rej=get_task_subquery(rejected=True),

            m_total=get_meeting_subquery(),
            m_att=get_meeting_subquery(attended=True),
            m_unex=get_meeting_subquery(attended=False, excused=False),
            m_ex=get_meeting_subquery(attended=False, excused=True),

            e_total=get_expense_subquery(),
            e_pend=get_expense_subquery(status='pending'),
            e_paid=get_expense_subquery(status='paid'),
            e_conf=get_expense_subquery(status='confirmed'),
            e_canc=get_expense_subquery(status='cancelled'),

            pay_total=get_payroll_subquery('total_amount'),
            pay_kpi=get_payroll_subquery('kpi_bonus'),
            pay_pen=get_payroll_subquery('penalty_amount')
        )

    def get_report(self, obj):
        return {
            "projects": {
                "completed": getattr(obj, 'p_comp', 0) or 0,
                "in_progress": getattr(obj, 'p_active', 0) or 0,
                "cancelled": getattr(obj, 'p_canc', 0) or 0,
                "overdue": getattr(obj, 'p_over', 0) or 0,
                "planning": getattr(obj, 'p_plan', 0) or 0,
            },
            "tasks": {
                "total": getattr(obj, 't_total', 0) or 0,
                "todo": getattr(obj, 't_todo', 0) or 0,
                "in_progress": getattr(obj, 't_prog', 0) or 0,
                "overdue": getattr(obj, 't_over', 0) or 0,
                "done": getattr(obj, 't_done', 0) or 0,
                "production": getattr(obj, 't_prod', 0) or 0,
                "checked": getattr(obj, 't_check', 0) or 0,
                "rejected": getattr(obj, 't_rej', 0) or 0,
            },
            "meetings": {
                "total": getattr(obj, 'm_total', 0) or 0,
                "attended": getattr(obj, 'm_att', 0) or 0,
                "missed_unexcused": getattr(obj, 'm_unex', 0) or 0,
                "missed_excused": getattr(obj, 'm_ex', 0) or 0,
            },
            "expense_requests_amount": {
                "total": getattr(obj, 'e_total', 0) or 0,
                "pending": getattr(obj, 'e_pend', 0) or 0,
                "paid": getattr(obj, 'e_paid', 0) or 0,
                "confirmed": getattr(obj, 'e_conf', 0) or 0,
                "cancelled": getattr(obj, 'e_canc', 0) or 0,
            },
            "payroll_amount": {
                "total": getattr(obj, 'pay_total', 0) or 0,
                "kpi_bonuses": getattr(obj, 'pay_kpi', 0) or 0,
                "penalty_amount": getattr(obj, 'pay_pen', 0) or 0,
            }
        }


class ProjectComprehensiveReportSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    manager_name = serializers.CharField(source='manager.username', read_only=True)
    employees_names = serializers.SerializerMethodField()
    testers_names = serializers.SerializerMethodField()
    task_stats = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            'id', 'prefix', 'title', 'description', 'deadline', 'status',
            'project_price', 'created_by_name', 'manager_name',
            'employees_names', 'testers_names', 'task_stats'
        )

    def get_employees_names(self, obj):
        return ", ".join([u.username for u in obj.employees.all()])

    def get_testers_names(self, obj):
        return ", ".join([u.username for u in obj.testers.all()])

    def get_task_stats(self, obj):
        return {
            "total": getattr(obj, 't_total', 0) or 0,
            "todo": getattr(obj, 't_todo', 0) or 0,
            "in_progress": getattr(obj, 't_prog', 0) or 0,
            "overdue": getattr(obj, 't_over', 0) or 0,
            "done": getattr(obj, 't_done', 0) or 0,
            "production": getattr(obj, 't_prod', 0) or 0,
            "checked": getattr(obj, 't_check', 0) or 0,
            "rejected": getattr(obj, 't_rej', 0) or 0,
        }

    @staticmethod
    def setup_eager_loading(queryset):
        def get_task_subquery(status=None, rejected=False):
            qs = Task.objects.filter(project=OuterRef('pk'), is_active=True, is_deleted=False)

            if status:
                qs = qs.filter(status=status)

            if rejected:
                qs = qs.filter(reopened_count__gt=0)

            return Subquery(qs.values('project').annotate(cnt=Count('pk')).values('cnt'), output_field=IntegerField())

        return queryset.select_related('created_by', 'manager').prefetch_related('employees', 'testers').annotate(
            t_total=get_task_subquery(),
            t_todo=get_task_subquery(status='todo'),
            t_prog=get_task_subquery(status='in_progress'),
            t_over=get_task_subquery(status='overdue'),
            t_done=get_task_subquery(status='done'),
            t_prod=get_task_subquery(status='production'),
            t_check=get_task_subquery(status='checked'),
            t_rej=get_task_subquery(rejected=True)
        )


class ExpenseRequestReportSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source='user.username', read_only=True)
    accountant = serializers.CharField(source='accountant.username', read_only=True)
    project = serializers.CharField(source='project.title', read_only=True)
    expense_category = serializers.CharField(source='expense_category.title', read_only=True)

    class Meta:
        model = ExpenseRequest
        fields = (
            'id', 'user', 'accountant', 'project',
            'type', 'expense_category', 'amount',
            'reason', 'cancel_reason', 'payment_method',
            'card_number', 'status',
            'created_at', 'paid_at', 'confirmed_at', 'cancelled_at'
        )

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.select_related('user', 'accountant', 'project', 'expense_category')


class PayrollReportSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source='user.username', read_only=True)
    accountant = serializers.CharField(source='accountant.username', read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Payroll
        fields = (
            'id', 'user', 'accountant', 'month',
            'fixed_salary', 'kpi_bonus', 'penalty_amount', 'total_amount',
            'status', 'created_at', 'confirmed_at'
        )

    def get_status(self, obj):
        return "Hisoblangan" if obj.is_confirmed else "Hisoblanmagan"

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.select_related('user', 'accountant')


class TaskReportSerializer(serializers.ModelSerializer):
    project = serializers.CharField(source='project.title', read_only=True)
    prefix = serializers.CharField(source='project.prefix', read_only=True)
    assignee = serializers.CharField(source='assignee.username', read_only=True)
    created_by = serializers.CharField(source='created_by.username', read_only=True)
    position = serializers.CharField(source='position.name', read_only=True)

    class Meta:
        model = Task
        fields = (
            'id', 'uid', 'project', 'prefix', 'sprint', 'title',
            'assignee', 'priority', 'status', 'type', 'task_price',
            'penalty_percentage', 'deadline', 'created_at',
            'created_by', 'position', 'reopened_count', 'rejection_reason'
        )

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.select_related('project', 'assignee', 'created_by', 'position')
