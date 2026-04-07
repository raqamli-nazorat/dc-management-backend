from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import (UserViewSet, ProfileView, ChangePasswordView,
                    MyTokenObtainPairView, MyTokenRefreshView,
                    SetPinView, CheckPinView)

router = SimpleRouter()
router.register('users', UserViewSet)

urlpatterns = [
    path('users/me/', ProfileView.as_view(), name='profile'),
    path('users/me/change-password/', ChangePasswordView.as_view(), name='change-password'),

    path('users/me/pin/set/', SetPinView.as_view(), name='set-pin'),
    path('users/me/pin/verify/', CheckPinView.as_view(), name='verify-pin'),

    path('', include(router.urls)),

    path('auth/login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', MyTokenRefreshView.as_view(), name='token_refresh'),
]
