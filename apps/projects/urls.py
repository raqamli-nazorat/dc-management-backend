from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import (ProjectShortViewSet, ProjectViewSet, TaskViewSet, TaskAttachmentViewSet,
                    MeetingViewSet, MeetingAttendanceViewSet, TaskRejectionFileViewSet)

router = SimpleRouter()
router.register('projects', ProjectViewSet, basename='projects')
router.register('project-shorts', ProjectShortViewSet, basename='projects-shorts')
router.register('tasks', TaskViewSet, basename='tasks')
router.register('task-attachments', TaskAttachmentViewSet, basename='task-attachments')
router.register('task-rejection-files', TaskRejectionFileViewSet, basename='task-rejection-files')
router.register('meetings', MeetingViewSet, basename='meetings')
router.register('meeting-attendance', MeetingAttendanceViewSet, basename='meeting-attendance')

urlpatterns = [
    path('', include(router.urls))
]
