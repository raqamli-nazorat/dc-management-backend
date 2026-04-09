from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import (UserViewSet, ProfileView, ChangePasswordView,
                    MyTokenObtainPairView, MyTokenRefreshView)

router = SimpleRouter()
router.register('users', UserViewSet)

urlpatterns = [
    path('users/me/', ProfileView.as_view(), name='profile'),
    path('users/me/change-password/', ChangePasswordView.as_view(), name='change-password'),

    path('', include(router.urls)),

    path('auth/login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', MyTokenRefreshView.as_view(), name='token_refresh'),
]
