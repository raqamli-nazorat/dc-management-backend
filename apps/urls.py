from django.urls import path, include

urlpatterns = [
    path('', include('apps.users.urls')),
    path('', include('apps.projects.urls')),
    path('', include('apps.finance.urls')),
    path('', include('apps.audit.urls')),
    path('', include('apps.applications.urls')),
    path('', include('apps.notifications.urls')),
    path('', include('apps.reports.urls')),
    path('', include('apps.todos.urls')),
]
