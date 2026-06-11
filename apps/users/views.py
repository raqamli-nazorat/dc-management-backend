from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from rest_framework import viewsets, permissions, generics, filters, status, parsers
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.common.throttles import CustomScopedRateThrottle
from apps.common.mixins import SoftDeleteMixin

from .filters import UserFilter
from .permissions import IsAuditor, IsAdmin, IsManager, IsEmployee
from .serializers import (UserSerializer, UserPeriodStatsSerializer, UserEfficiencySerializer, ProfileSerializer,
                          UserShortSerializer,
                          ChangePasswordSerializer,
                          MyTokenRefreshSerializer, MyTokenObtainPairSerializer)

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

    def get_queryset(self):
        queryset = super().get_queryset()

        return queryset.exclude(is_superuser=True)

    def perform_destroy(self, instance):
        if instance.is_superuser:
            raise ValidationError({
                "detail": "Superadminni o'chirish mumkin emas!"
            })

        super().perform_destroy(instance)


@extend_schema(tags=['Users'], summary="Hamma uchun foydalanuvchilar ro'yxati")
class UserShortListView(generics.ListAPIView):
    queryset = User.objects.filter(is_active=True).exclude(is_superuser=True)
    serializer_class = UserShortSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = UserFilter
    search_fields = ['username', 'phone_number']
    ordering_fields = ['username', 'date_joined']
    ordering = ['username']


@extend_schema(tags=['Profile'])
class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser]
    http_method_names = ['get', 'patch']

    def get_object(self):
        return self.request.user


@extend_schema(
    tags=['Statistics'],
    parameters=[
        OpenApiParameter(
            name='months',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Oylarda davrni kiriting (masalan, 1, 3, 5). Default 1.',
            required=False,
            default=1,
        )
    ]
)
class UserPeriodStatsView(generics.RetrieveAPIView):
    serializer_class = UserPeriodStatsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


@extend_schema(
    tags=['Statistics'],
    parameters=[
        OpenApiParameter(
            name='months',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Oylarda davrni kiriting (masalan, 1, 3, 5). Default 1.',
            required=False,
            default=1,
        )
    ]
)
class UserEfficiencyView(generics.RetrieveAPIView):
    serializer_class = UserEfficiencySerializer
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

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        for throttle in self.get_throttles():
            if hasattr(throttle, 'get_cache_key') and hasattr(throttle, 'cache'):
                if hasattr(throttle, 'scope_attr'):
                    throttle.scope = getattr(self, throttle.scope_attr, None)
                cache_key = throttle.get_cache_key(request, view=self)
                if cache_key:
                    throttle.cache.delete(cache_key)

        return response


@extend_schema(tags=["Authorization"])
class MyTokenRefreshView(TokenRefreshView):
    serializer_class = MyTokenRefreshSerializer
