from django.db.models import Count, Q, Sum, OuterRef, Subquery, IntegerField, DecimalField
from django_filters import rest_framework as filters
from django.contrib.auth import get_user_model

from apps.projects.filters import NumberInFilter
from apps.projects.models import Project, Task, MeetingAttendance
from apps.finance.models import ExpenseRequest, Payroll

User = get_user_model()


class UserReportFilter(filters.FilterSet):
    users = NumberInFilter(field_name='id', lookup_expr='in', label="Xodimlar")
    region = NumberInFilter(field_name='region_id', lookup_expr='in', label="Viloyat")
    district = NumberInFilter(field_name='district_id', lookup_expr='in', label="Tuman")
    position = NumberInFilter(field_name='position_id', lookup_expr='in', label="Lavozim")
    roles = filters.CharFilter(method='filter_roles', label="Rollar")

    balance_min = filters.NumberFilter(field_name='balance', lookup_expr='gte', label="Balans (min)")
    balance_max = filters.NumberFilter(field_name='balance', lookup_expr='lte', label="Balans (max)")

    salary_min = filters.NumberFilter(field_name='fixed_salary', lookup_expr='gte', label="Maosh (min)")
    salary_max = filters.NumberFilter(field_name='fixed_salary', lookup_expr='lte', label="Maosh (max)")

    projects_min = filters.NumberFilter(method='filter_projects_count', label="Loyihalar soni (min)")
    projects_max = filters.NumberFilter(method='filter_projects_count', label="Loyihalar soni (max)")

    tasks_min = filters.NumberFilter(method='filter_tasks_count', label="Vazifalar soni (min)")
    tasks_max = filters.NumberFilter(method='filter_tasks_count', label="Vazifalar soni (max)")

    meetings_min = filters.NumberFilter(method='filter_meetings_count', label="Yig'ilishlar soni (min)")
    meetings_max = filters.NumberFilter(method='filter_meetings_count', label="Yig'ilishlar soni (max)")

    expenses_amount_min = filters.NumberFilter(method='filter_expenses_amount', label="Xarajatlar (min)")
    expenses_amount_max = filters.NumberFilter(method='filter_expenses_amount', label="Xarajatlar (max)")

    payrolls_amount_min = filters.NumberFilter(method='filter_payrolls_amount', label="Ish haqi (min)")
    payrolls_amount_max = filters.NumberFilter(method='filter_payrolls_amount', label="Ish haqi (max)")

    class Meta:
        model = User
        fields = []

    def filter_roles(self, queryset, name, value):
        if value:
            return queryset.filter(roles__contains=[value])
        return queryset

    def filter_projects_count(self, queryset, name, value):
        queryset = queryset.annotate(
            total_projects=(
                    Count('created_projects',
                          filter=Q(created_projects__is_active=True, created_projects__is_deleted=False),
                          distinct=True) +
                    Count('manager_projects',
                          filter=Q(manager_projects__is_active=True, manager_projects__is_deleted=False),
                          distinct=True) +
                    Count('employee_projects',
                          filter=Q(employee_projects__is_active=True, employee_projects__is_deleted=False),
                          distinct=True) +
                    Count('tester_projects',
                          filter=Q(tester_projects__is_active=True, tester_projects__is_deleted=False), distinct=True)
            )
        )

        if name == 'projects_min':
            return queryset.filter(total_projects__gte=value)
        return queryset.filter(total_projects__lte=value)

    def filter_tasks_count(self, queryset, name, value):
        subquery = Task.objects.filter(assignee=OuterRef('pk'), is_active=True, is_deleted=False).values(
            'assignee').annotate(
            cnt=Count('pk')).values('cnt')

        queryset = queryset.annotate(total_tasks=Subquery(subquery, output_field=IntegerField()))

        if name == 'tasks_min':
            return queryset.filter(total_tasks__gte=value)
        return queryset.filter(total_tasks__lte=value)

    def filter_meetings_count(self, queryset, name, value):
        subquery = MeetingAttendance.objects.filter(user=OuterRef('pk'), is_active=True).values('user').annotate(
            cnt=Count('pk')).values('cnt')

        queryset = queryset.annotate(total_meetings=Subquery(subquery, output_field=IntegerField()))

        if name == 'meetings_min':
            return queryset.filter(total_meetings__gte=value)
        return queryset.filter(total_meetings__lte=value)

    def filter_expenses_amount(self, queryset, name, value):
        subquery = ExpenseRequest.objects.filter(user=OuterRef('pk'), is_active=True).values('user').annotate(
            total=Sum('amount')).values('total')

        queryset = queryset.annotate(total_expenses=Subquery(subquery, output_field=DecimalField()))

        if name == 'expenses_amount_min':
            return queryset.filter(total_expenses__gte=value)
        return queryset.filter(total_expenses__lte=value)

    def filter_payrolls_amount(self, queryset, name, value):
        subquery = Payroll.objects.filter(user=OuterRef('pk'), is_active=True).values('user').annotate(
            total=Sum('total_amount')).values('total')

        queryset = queryset.annotate(total_payroll=Subquery(subquery, output_field=DecimalField()))

        if name == 'payrolls_amount_min':
            return queryset.filter(total_payroll__gte=value)
        return queryset.filter(total_payroll__lte=value)


class ProjectReportFilter(filters.FilterSet):
    title = filters.CharFilter(lookup_expr='icontains', label="Nomi")
    prefix = filters.CharFilter(lookup_expr='icontains', label="Titul (Prefix)")
    status = filters.ChoiceFilter(choices=[], label="Holati")

    deadline_min = filters.DateTimeFilter(field_name='deadline', lookup_expr='gte', label="Muddati (dan)")
    deadline_max = filters.DateTimeFilter(field_name='deadline', lookup_expr='lte', label="Muddati (gacha)")

    price_min = filters.NumberFilter(field_name='project_price', lookup_expr='gte', label="Boshqaruvchi bonusi (dan)")
    price_max = filters.NumberFilter(field_name='project_price', lookup_expr='lte', label="Boshqaruvchi bonusi (gacha)")

    created_by = filters.ModelChoiceFilter(queryset=get_user_model().objects.all(), label="Muallif")
    manager = filters.ModelChoiceFilter(queryset=get_user_model().objects.all(), label="Boshqaruvchi")

    class Meta:
        model = Project
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.projects.models import ProjectStatus
        self.filters['status'].extra['choices'] = ProjectStatus.choices
