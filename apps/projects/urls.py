from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import (ProjectShortViewSet, ProjectViewSet, TaskViewSet, TaskAttachmentViewSet,
                    MeetingViewSet, MeetingAttendanceViewSet, MeetingAttendanceReasonViewSet)

router = SimpleRouter()
router.register('projects', ProjectViewSet, basename='projects')
router.register('project-shorts', ProjectShortViewSet, basename='projects-shorts')
router.register('tasks', TaskViewSet, basename='tasks')
router.register('task-attachments', TaskAttachmentViewSet, basename='task-attachments')
router.register('meetings', MeetingViewSet, basename='meetings')
router.register('meeting-attendance', MeetingAttendanceViewSet, basename='meeting-attendance')
router.register('meeting-reasons', MeetingAttendanceReasonViewSet, basename='meeting-reasons')

urlpatterns = [
    path('', include(router.urls))
]
