from django.urls import path, include

urlpatterns = [
    path('', include('apps.users.urls')),
    path('', include('apps.projects.urls')),
    # path('', include('apps.finance.urls')),
    path('', include('apps.audit.urls')),
]