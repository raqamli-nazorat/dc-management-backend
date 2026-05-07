from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from rest_framework import viewsets, permissions, generics, filters, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.common.throttles import CustomScopedRateThrottle
from apps.common.mixins import SoftDeleteMixin

from .filters import UserFilter
from .models import Role
from .permissions import IsAuditor, IsAdmin, IsManager, IsEmployee
from .serializers import (UserSerializer, UserPeriodStatsSerializer, UserEfficiencySerializer, ProfileSerializer,
                          SocialLinksSerializer,
                          ChangePasswordSerializer,
                          MyTokenRefreshSerializer, MyTokenObtainPairSerializer, CardNumberSerializer,
                          ChangeActiveRoleSerializer)

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

        return queryset.exclude(
            Q(roles__contains=[Role.SUPERADMIN]) | Q(is_superuser=True)
        )

    def perform_destroy(self, instance):
        if instance.is_superuser or instance.has_any_role(Role.SUPERADMIN):
            raise ValidationError({
                "detail": "Superadminni o'chirish mumkin emas!"
            })

        super().perform_destroy(instance)


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
class CardNumberView(generics.UpdateAPIView):
    serializer_class = CardNumberSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['put']

    def get_object(self):
        return self.request.user

    def put(self, request, *args, **kwargs):
        serializer = CardNumberSerializer(
            data=request.data,
            instance=self.get_object(),
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Karta raqam muvaffaqiyatli yangilandi."
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Profile'])
class ChangeActiveRoleView(generics.UpdateAPIView):
    serializer_class = ChangeActiveRoleSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['put']

    def get_object(self):
        return self.request.user

    def put(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            instance=self.get_object(),
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()

            active_role_display = self.request.user.get_active_role_display()

            return Response({
                "message": f"Aktiv rol '{active_role_display}'ga muvaffaqiyatli o'zgartirildi.",
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Profile'])
class ProfileView(generics.RetrieveAPIView):
    serializer_class = ProfileSerializer
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
class UserPeriodStatsView(generics.RetrieveAPIView):
    serializer_class = UserPeriodStatsSerializer
    permission_classes = [IsEmployee | IsManager]

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


@extend_schema(tags=["Authorization"])
class MyTokenRefreshView(TokenRefreshView):
    serializer_class = MyTokenRefreshSerializer
