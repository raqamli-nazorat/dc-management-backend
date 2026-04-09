from rest_framework.routers import SimpleRouter

from .views import AuditLogViewSet

router = SimpleRouter()
router.register('auditlog', AuditLogViewSet)

urlpatterns = router.urls