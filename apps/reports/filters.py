from django.db.models import Count, Q, Sum, OuterRef, Subquery, IntegerField, DecimalField, Value
from django.db.models.functions import Coalesce
from django_filters import rest_framework as filters
from django.contrib.auth import get_user_model

from apps.projects.filters import NumberInFilter, CharInFilter
from apps.projects.models import Project, Task, MeetingAttendance, ProjectStatus, TaskStatus, Priority, Type
from apps.finance.models import ExpenseRequest, Payroll, ExpenseType, PaymentMethod, Status as ExpenseStatus

User = get_user_model()


class UserReportFilter(filters.FilterSet):
    users = NumberInFilter(field_name='id', lookup_expr='in', label="Xodimlar")
    region = NumberInFilter(field_name='region_id', lookup_expr='in', label="Viloyat")
    district = NumberInFilter(field_name='district_id', lookup_expr='in', label="Tuman")
    position = NumberInFilter(field_name='position_id', lookup_expr='in', label="Lavozim")
    roles = filters.CharFilter(method='filter_roles', label="Rollar")

    joined_min = filters.DateTimeFilter(field_name='date_joined', lookup_expr='gte', label="Qo'shilgan vaqt (dan)")
    joined_max = filters.DateTimeFilter(field_name='date_joined', lookup_expr='lte', label="Qo'shilgan vaqt (gacha)")

    balance_min = filters.NumberFilter(field_name='balance', lookup_expr='gte', label="Balans (min)")
    balance_max = filters.NumberFilter(field_name='balance', lookup_expr='lte', label="Balans (max)")

    salary_min = filters.NumberFilter(field_name='fixed_salary', lookup_expr='gte', label="Maosh (min)")
    salary_max = filters.NumberFilter(field_name='fixed_salary', lookup_expr='lte', label="Maosh (max)")

    projects_min = filters.NumberFilter(method='filter_projects_count', label="Loyihalar soni (min)")
    projects_max = filters.NumberFilter(method='filter_projects_count', label="Loyihalar soni (max)")
    project_status = filters.ChoiceFilter(choices=ProjectStatus.choices, method='filter_dummy', label="Loyiha holati")

    tasks_min = filters.NumberFilter(method='filter_tasks_count', label="Vazifalar soni (min)")
    tasks_max = filters.NumberFilter(method='filter_tasks_count', label="Vazifalar soni (max)")
    task_status = filters.ChoiceFilter(choices=TaskStatus.choices, method='filter_dummy', label="Vazifa holati")

    meetings_min = filters.NumberFilter(method='filter_meetings_count', label="Yig'ilishlar soni (min)")
    meetings_max = filters.NumberFilter(method='filter_meetings_count', label="Yig'ilishlar soni (max)")
    meetings_status = filters.ChoiceFilter(
        choices=[
            ('attended', 'Qatnashgan'),
            ('absent_reason', 'Sababli qatnashmagan'),
            ('absent_no_reason', 'Sababsiz qatnashmagan'),
        ],
        method='filter_dummy',
        label="Ishtirok holati"
    )

    expenses_amount_min = filters.NumberFilter(method='filter_expenses_amount', label="Xarajatlar (min)")
    expenses_amount_max = filters.NumberFilter(method='filter_expenses_amount', label="Xarajatlar (max)")
    expense_status = filters.ChoiceFilter(
        choices=[
            ('all', 'Jami'),
            ('pending', 'Kutilmoqda'),
            ('confirmed', 'To\'langan'),
            ('paid_unconfirmed', 'To\'langan (tasdiqlanmagan)'),
            ('cancelled', 'Bekor qilingan'),
        ],
        method='filter_dummy',
        label="Xarajat holati"
    )

    payrolls_amount_min = filters.NumberFilter(method='filter_payrolls_amount', label="Ish haqi (min)")
    payrolls_amount_max = filters.NumberFilter(method='filter_payrolls_amount', label="Ish haqi (max)")
    payroll_type = filters.ChoiceFilter(
        choices=[
            ('total', 'Jami maosh'),
            ('kpi', 'KPI Bonus'),
            ('penalty', 'Jarima miqdori'),
        ],
        method='filter_dummy',
        label="Ish haqi turi"
    )

    class Meta:
        model = User
        fields = []

    def filter_dummy(self, queryset, name, value):
        return queryset

    def filter_roles(self, queryset, name, value):
        if value:
            return queryset.filter(roles__contains=[value])
        return queryset

    def filter_projects_count(self, queryset, name, value):
        p_status = self.data.get('project_status')

        def get_q(prefix):
            q = Q(**{f"{prefix}__is_active": True, f"{prefix}__is_deleted": False})
            if p_status:
                q &= Q(**{f"{prefix}__status": p_status})
            return q

        queryset = queryset.annotate(
            total_projects=(
                    Count('created_projects', filter=get_q('created_projects'), distinct=True) +
                    Count('manager_projects', filter=get_q('manager_projects'), distinct=True) +
                    Count('employee_projects', filter=get_q('employee_projects'), distinct=True) +
                    Count('tester_projects', filter=get_q('tester_projects'), distinct=True)
            )
        )

        if name == 'projects_min':
            return queryset.filter(total_projects__gte=value)
        return queryset.filter(total_projects__lte=value)

    def filter_tasks_count(self, queryset, name, value):
        t_status = self.data.get('task_status')
        filters_q = Q(assignee=OuterRef('pk'), is_active=True, is_deleted=False)

        if t_status:
            if t_status == TaskStatus.REJECTED:
                filters_q &= Q(reopened_count__gt=0)
            else:
                filters_q &= Q(status=t_status)

        subquery = Task.objects.filter(filters_q).values('assignee').annotate(
            cnt=Count('pk')).values('cnt')

        queryset = queryset.annotate(total_tasks=Coalesce(Subquery(subquery, output_field=IntegerField()), Value(0)))

        if name == 'tasks_min':
            return queryset.filter(total_tasks__gte=value)
        return queryset.filter(total_tasks__lte=value)

    def filter_meetings_count(self, queryset, name, value):
        status = self.data.get('meetings_status')

        filters_q = Q(user=OuterRef('pk'), is_active=True)

        if status:
            if status == 'attended':
                filters_q &= Q(is_attended=True)

            elif status == 'absent_reason':
                filters_q &= Q(is_attended=False) & ~Q(absence_reason__isnull=True) & ~Q(absence_reason='')

            elif status == 'absent_no_reason':
                filters_q &= Q(is_attended=False) & (Q(absence_reason__isnull=True) | Q(absence_reason=''))

        subquery = MeetingAttendance.objects.filter(filters_q).values('user').annotate(
            cnt=Count('pk')).values('cnt')

        queryset = queryset.annotate(
            total_meetings=Coalesce(Subquery(subquery, output_field=IntegerField()), Value(0))
        )

        if name == 'meetings_min':
            return queryset.filter(total_meetings__gte=value)
        return queryset.filter(total_meetings__lte=value)

    def filter_expenses_amount(self, queryset, name, value):
        e_status = self.data.get('expense_status', 'all')

        filters_q = Q(user=OuterRef('pk'), is_active=True)

        if e_status == 'pending':
            filters_q &= Q(status=ExpenseStatus.PENDING)
        elif e_status == 'confirmed':
            filters_q &= Q(status=ExpenseStatus.CONFIRMED)
        elif e_status == 'paid_unconfirmed':
            filters_q &= Q(status=ExpenseStatus.PAID)
        elif e_status == 'cancelled':
            filters_q &= Q(status=ExpenseStatus.CANCELLED)

        subquery = ExpenseRequest.objects.filter(filters_q).values('user').annotate(
            total=Sum('amount')).values('total')

        queryset = queryset.annotate(
            total_expenses=Coalesce(
                Subquery(subquery, output_field=DecimalField()),
                Value(0, output_field=DecimalField())
            )
        )

        if name == 'expenses_amount_min':
            return queryset.filter(total_expenses__gte=value)
        return queryset.filter(total_expenses__lte=value)

    def filter_payrolls_amount(self, queryset, name, value):
        p_type = self.data.get('payroll_type', 'total')

        sum_field = 'total_amount'
        if p_type == 'kpi':
            sum_field = 'kpi_bonus'
        elif p_type == 'penalty':
            sum_field = 'penalty_amount'

        subquery = Payroll.objects.filter(
            user=OuterRef('pk'),
            is_active=True,
            is_confirmed=True
        ).values('user').annotate(
            total=Sum(sum_field)
        ).values('total')

        queryset = queryset.annotate(
            selected_payroll_amount=Coalesce(
                Subquery(subquery, output_field=DecimalField()),
                Value(0, output_field=DecimalField())
            )
        )

        if name == 'payrolls_amount_min':
            return queryset.filter(selected_payroll_amount__gte=value)
        return queryset.filter(selected_payroll_amount__lte=value)


class ProjectReportFilter(filters.FilterSet):
    title = filters.CharFilter(lookup_expr='icontains', label="Nomi")
    prefix = filters.CharFilter(lookup_expr='icontains', label="Titul (Prefix)")
    status = filters.ChoiceFilter(choices=[], label="Holati")

    deadline_min = filters.DateTimeFilter(field_name='deadline', lookup_expr='gte', label="Muddati (dan)")
    deadline_max = filters.DateTimeFilter(field_name='deadline', lookup_expr='lte', label="Muddati (gacha)")

    price_min = filters.NumberFilter(field_name='project_price', lookup_expr='gte', label="Boshqaruvchi bonusi (dan)")
    price_max = filters.NumberFilter(field_name='project_price', lookup_expr='lte', label="Boshqaruvchi bonusi (gacha)")

    created_by = NumberInFilter(field_name='created_by_id', lookup_expr='in', label="Mualliflar")
    manager = NumberInFilter(field_name='manager_id', lookup_expr='in', label="Boshqaruvchilar")
    employees = NumberInFilter(field_name='employees', lookup_expr='in', label="Xodimlar")
    testers = NumberInFilter(field_name='testers', lookup_expr='in', label="Sinovchilar")

    class Meta:
        model = Project
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.projects.models import ProjectStatus
        self.filters['status'].extra['choices'] = ProjectStatus.choices


class ExpenseReportFilter(filters.FilterSet):
    user = NumberInFilter(field_name='user_id', lookup_expr='in', label="Foydalanuvchi")
    accountant = NumberInFilter(field_name='accountant_id', lookup_expr='in', label="Hisobchi")
    project = NumberInFilter(field_name='project_id', lookup_expr='in', label="Loyiha")
    expense_category = NumberInFilter(field_name='expense_category_id', lookup_expr='in', label="Kategoriya")

    type = CharInFilter(field_name='type', lookup_expr='in', label="Xarajat turi")
    payment_method = CharInFilter(field_name='payment_method', lookup_expr='in', label="To'lov turi")
    status = CharInFilter(field_name='status', lookup_expr='in', label="Holati")

    amount_min = filters.NumberFilter(field_name='amount', lookup_expr='gte', label="Miqdori (min)")
    amount_max = filters.NumberFilter(field_name='amount', lookup_expr='lte', label="Miqdori (max)")

    created_at_min = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte', label="Yaratilgan vaqt (dan)")
    created_at_max = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte', label="Yaratilgan vaqt (gacha)")

    paid_at_min = filters.DateTimeFilter(field_name='paid_at', lookup_expr='gte', label="To'langan vaqt (dan)")
    paid_at_max = filters.DateTimeFilter(field_name='paid_at', lookup_expr='lte', label="To'langan vaqt (gacha)")

    confirmed_at_min = filters.DateTimeFilter(field_name='confirmed_at', lookup_expr='gte',
                                              label="Tasdiqlangan vaqt (dan)")
    confirmed_at_max = filters.DateTimeFilter(field_name='confirmed_at', lookup_expr='lte',
                                              label="Tasdiqlangan vaqt (gacha)")

    cancelled_at_min = filters.DateTimeFilter(field_name='cancelled_at', lookup_expr='gte',
                                              label="Bekor qilingan vaqt (dan)")
    cancelled_at_max = filters.DateTimeFilter(field_name='cancelled_at', lookup_expr='lte',
                                              label="Bekor qilingan vaqt (gacha)")

    class Meta:
        model = ExpenseRequest
        fields = []


class PayrollReportFilter(filters.FilterSet):
    user = NumberInFilter(field_name='user_id', lookup_expr='in', label="Foydalanuvchi")
    accountant = NumberInFilter(field_name='accountant_id', lookup_expr='in', label="Hisobchi")
    is_confirmed = filters.BooleanFilter(field_name='is_confirmed', label="Tasdiqlanganmi?")

    month_year = filters.CharFilter(method='filter_by_month_year', label="Oy va yil (YYYY-MM)")

    total_amount_min = filters.NumberFilter(field_name='total_amount', lookup_expr='gte', label="Jami miqdori (min)")
    total_amount_max = filters.NumberFilter(field_name='total_amount', lookup_expr='lte', label="Jami miqdori (max)")

    salary_min = filters.NumberFilter(field_name='fixed_salary', lookup_expr='gte', label="Oylik maosh (min)")
    salary_max = filters.NumberFilter(field_name='fixed_salary', lookup_expr='lte', label="Oylik maosh (max)")

    penalty_min = filters.NumberFilter(field_name='penalty_amount', lookup_expr='gte', label="Jarima miqdori (min)")
    penalty_max = filters.NumberFilter(field_name='penalty_amount', lookup_expr='lte', label="Jarima miqdori (max)")

    kpi_min = filters.NumberFilter(field_name='kpi_bonus', lookup_expr='gte', label="KPI bonus (min)")
    kpi_max = filters.NumberFilter(field_name='kpi_bonus', lookup_expr='lte', label="KPI bonus (max)")

    created_at_min = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte', label="Hisoblangan vaqt (dan)")
    created_at_max = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte',
                                            label="Hisoblangan vaqt (gacha)")

    confirmed_at_min = filters.DateTimeFilter(field_name='confirmed_at', lookup_expr='gte',
                                              label="Tasdiqlangan vaqt (dan)")
    confirmed_at_max = filters.DateTimeFilter(field_name='confirmed_at', lookup_expr='lte',
                                              label="Tasdiqlangan vaqt (gacha)")

    class Meta:
        model = Payroll
        fields = []

    def filter_by_month_year(self, queryset, name, value):
        if not value:
            return queryset
        try:
            year, month = value.split('-')
            return queryset.filter(month__year=year, month__month=month)
        except (ValueError, TypeError):
            return queryset


class TaskReportFilter(filters.FilterSet):
    project = NumberInFilter(field_name='project_id', lookup_expr='in', label="Loyiha")
    assignee = NumberInFilter(field_name='assignee_id', lookup_expr='in', label="Topshiruvchi")
    created_by = NumberInFilter(field_name='created_by_id', lookup_expr='in', label="Yaratuvchi")
    position = NumberInFilter(field_name='position_id', lookup_expr='in', label="Lavozim")

    priority = CharInFilter(field_name='priority', lookup_expr='in', label="Darajasi")
    status = CharInFilter(method='filter_status', label="Holati")
    type = CharInFilter(field_name='type', lookup_expr='in', label="Turi")
    sprint = NumberInFilter(field_name='sprint', lookup_expr='in', label="Sprint")

    penalty_min = filters.NumberFilter(field_name='penalty_percentage', lookup_expr='gte', label="Jarima foizi (min)")
    penalty_max = filters.NumberFilter(field_name='penalty_percentage', lookup_expr='lte', label="Jarima foizi (max)")

    price_min = filters.NumberFilter(field_name='task_price', lookup_expr='gte', label="Vazifa narxi (min)")
    price_max = filters.NumberFilter(field_name='task_price', lookup_expr='lte', label="Vazifa narxi (max)")

    deadline_min = filters.DateTimeFilter(field_name='deadline', lookup_expr='gte', label="Muddati (dan)")
    deadline_max = filters.DateTimeFilter(field_name='deadline', lookup_expr='lte', label="Muddati (gacha)")

    reopened_min = filters.NumberFilter(field_name='reopened_count', lookup_expr='gte', label="Qaytishlar soni (min)")
    reopened_max = filters.NumberFilter(field_name='reopened_count', lookup_expr='lte', label="Qaytishlar soni (max)")

    created_at_min = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte', label="Yaratilgan sana (dan)")
    created_at_max = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte', label="Yaratilgan sana (gacha)")

    class Meta:
        model = Task
        fields = []

    def filter_status(self, queryset, name, value):
        if not value:
            return queryset

        q_objects = Q()
        if TaskStatus.REJECTED in value:
            q_objects |= Q(reopened_count__gt=0)
            remaining_statuses = [s for s in value if s != TaskStatus.REJECTED]
            if remaining_statuses:
                q_objects |= Q(status__in=remaining_statuses)
        else:
            q_objects |= Q(status__in=value)

        return queryset.filter(q_objects)
