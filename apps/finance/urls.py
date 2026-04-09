from rest_framework.routers import SimpleRouter
from .views import ExpenseRequestViewSet, ExpenseCategoryViewSet, LedgerViewSet, PayrollViewSet

router = SimpleRouter()
router.register('expense-category', ExpenseCategoryViewSet)
router.register('expense-request', ExpenseRequestViewSet)
router.register('ledger', LedgerViewSet)
router.register('payroll', PayrollViewSet)

urlpatterns = router.urls
