from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, generics, filters, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.common.throttles import CustomScopedRateThrottle
from apps.common.mixins import SoftDeleteMixin

from .filters import UserFilter
from .permissions import IsAdmin, IsAuditor, IsEmployee, IsManager
from .serializers import (UserSerializer, ProfileSerializer, SocialLinksSerializer, ChangePasswordSerializer,
                          MyTokenRefreshSerializer, MyTokenObtainPairSerializer, UserStatsSerializer)

User = get_user_model()


@extend_schema(tags=['Users'], summary="Admin")
class UserViewSet(SoftDeleteMixin, viewsets.ModelViewSet):
    queryset = User.objects.filter(is_active=True)
    serializer_class = UserSerializer
    
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = UserFilter
    search_fields = ['username']
    ordering_fields = ['username']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [(IsAdmin | IsAuditor)()]
        return [IsAdmin()]


@extend_schema(tags=['Profile'])
class SocialLinksView(generics.UpdateAPIView):
    serializer_class = SocialLinksSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['put']

    def get_object(self):
        return self.request.user

    def put(self, request, *args, **kwargs):
        serializer = SocialLinksSerializer(
            data=request.data,
            instance=self.get_object(),
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Ijtimoiy tarmoqlar muvaffaqiyatli yangilandi."
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Profile'])
class ProfileView(generics.RetrieveAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


@extend_schema(tags=['Profile'])
class UserStatsView(generics.RetrieveAPIView):
    serializer_class = UserStatsSerializer
    permission_classes = [IsEmployee | IsManager]

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Profile"])
class ChangePasswordView(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['put']

    def get_object(self):
        return self.request.user

    def put(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Parol muvaffaqiyatli o'zgartirildi."
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Authorization"])
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [CustomScopedRateThrottle]
    throttle_scope = 'login'


@extend_schema(tags=["Authorization"])
class MyTokenRefreshView(TokenRefreshView):
    serializer_class = MyTokenRefreshSerializer
