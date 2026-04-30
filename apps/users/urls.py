from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import (UserViewSet, ProfileView, SocialLinksView, CardNumberView, ChangeActiveRoleView, ChangePasswordView,
                    MyTokenObtainPairView, MyTokenRefreshView, UserPeriodStatsView, UserEfficiencyView)

router = SimpleRouter()
router.register('users', UserViewSet)

urlpatterns = [
    path('users/me/', ProfileView.as_view(), name='profile'),
    path('users/me/social-links/', SocialLinksView.as_view(), name='social-links'),
    path('users/me/card-number/', CardNumberView.as_view(), name='card-number'),
    path('users/me/change-role/', ChangeActiveRoleView.as_view(), name='change-role'),
    path('users/me/change-password/', ChangePasswordView.as_view(), name='change-password'),

    path('users/me/period-statistics/', UserPeriodStatsView.as_view(), name='user-period-stats'),
    path('users/me/efficiency/', UserEfficiencyView.as_view(), name='user-efficiency'),

    path('', include(router.urls)),

    path('auth/login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', MyTokenRefreshView.as_view(), name='token_refresh'),
]
