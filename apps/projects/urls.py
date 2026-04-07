from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import ProjectViewSet, TaskViewSet, TaskAttachmentViewSet

router = SimpleRouter()
router.register('projects', ProjectViewSet, basename='projects')
router.register('tasks', TaskViewSet, basename='tasks')
router.register('task-attachments', TaskAttachmentViewSet, basename='task-attachments')

urlpatterns = [
    path('', include(router.urls))
]
