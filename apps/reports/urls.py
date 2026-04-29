from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import (
    UserReportReadOnlyViewSet,
    ProjectReportReadOnlyViewSet,
    ExpenseReportReadOnlyViewSet,
    PayrollReportReadOnlyViewSet,
    TaskReportReadOnlyViewSet
)

router = SimpleRouter()
router.register('reports/users', UserReportReadOnlyViewSet, basename='user-reports')
router.register('reports/projects', ProjectReportReadOnlyViewSet, basename='project-reports')
router.register('reports/expenses', ExpenseReportReadOnlyViewSet, basename='expense-reports')
router.register('reports/payrolls', PayrollReportReadOnlyViewSet, basename='payroll-reports')
router.register('reports/tasks', TaskReportReadOnlyViewSet, basename='task-reports')

urlpatterns = [
    path('', include(router.urls)),
]
