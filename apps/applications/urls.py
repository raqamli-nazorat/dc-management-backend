from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import (ApplicationCreateView, ApplicationStatusUpdateView,
                    RegionViewSet, DirectionViewSet)

router = SimpleRouter()
router.register('regions', RegionViewSet)
router.register('directions', DirectionViewSet)

urlpatterns = [
    path('applications/', include(router.urls)),
    path('applications/', ApplicationCreateView.as_view(), name='application-create'),
    path('applications/<int:pk>/status/', ApplicationStatusUpdateView.as_view(), name='application-status-update'),
]
