from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import (ApplicationView, ApplicationDetailView,
                    RegionViewSet, DistrictViewSet, DirectionViewSet)

router = SimpleRouter()
router.register('regions', RegionViewSet)
router.register('districts', DistrictViewSet)
router.register('directions', DirectionViewSet)

urlpatterns = [
    path('applications/', include(router.urls)),
    path('applications/', ApplicationView.as_view(), name='application'),
    path('applications/<int:pk>/', ApplicationDetailView.as_view(), name='application-detail'),
]
