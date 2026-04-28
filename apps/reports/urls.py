from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import UserReportReadOnlyViewSet, ProjectReportReadOnlyViewSet

router = SimpleRouter()
router.register('reports/users', UserReportReadOnlyViewSet, basename='user-reports')
router.register('reports/projects', ProjectReportReadOnlyViewSet, basename='project-reports')

urlpatterns = [
    path('', include(router.urls)),
]
