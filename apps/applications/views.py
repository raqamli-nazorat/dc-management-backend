from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import parsers, viewsets, filters
from rest_framework.filters import SearchFilter
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny

from apps.applications.filters import ApplicationFilter
from apps.applications.models import Region, District, Position, Application
from apps.applications.serializers import (RegionSerializer, DistrictSerializer, PositionSerializer,
                                           ApplicationSerializer, ApplicationStatusUpdateSerializer)
from apps.users.permissions import IsAdmin, IsManager, IsSuperAdmin
from apps.users.models import Role

from apps.common.mixins import SoftDeleteMixin


class ActiveObjectsMixin:
    admin_roles = [Role.SUPERADMIN, Role.ADMIN, Role.MANAGER]

    def get_permissions(self):
        if self.action == 'list':
            return [AllowAny()]
        return [(IsSuperAdmin | IsAdmin | IsManager)()]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()

        if user.is_authenticated and user.has_role(*self.admin_roles):
            return queryset
        return queryset.filter(is_application=True)


@extend_schema(tags=['Region'])
class RegionViewSet(SoftDeleteMixin, ActiveObjectsMixin, viewsets.ModelViewSet):
    queryset = Region.objects.filter(is_active=True)
    serializer_class = RegionSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']


@extend_schema(tags=['District'])
class DistrictViewSet(SoftDeleteMixin, ActiveObjectsMixin, viewsets.ModelViewSet):
    queryset = District.objects.filter(is_active=True).select_related('region').all()
    serializer_class = DistrictSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['region']
    search_fields = ['name']


@extend_schema(tags=['Position'])
class PositionViewSet(SoftDeleteMixin, ActiveObjectsMixin, viewsets.ModelViewSet):
    queryset = Position.objects.filter(is_active=True)
    serializer_class = PositionSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']


@extend_schema(tags=['Application'])
class ApplicationView(ListCreateAPIView):
    serializer_class = ApplicationSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    permission_classes = (AllowAny,)
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = ApplicationFilter
    search_fields = ['full_name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [AllowAny()]
        return [(IsAdmin | IsManager)()]

    def get_queryset(self):
        return Application.objects.filter(is_active=True).select_related(
            'region', 'position', 'reviewed_by'
        )


@extend_schema(tags=['Application'])
class ApplicationDetailView(RetrieveUpdateAPIView):
    queryset = Application.objects.filter(is_active=True).select_related(
        'region', 'position', 'reviewed_by'
    )
    permission_classes = (IsAdmin | IsManager,)
    http_method_names = ('get', 'patch',)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return ApplicationSerializer
        return ApplicationStatusUpdateSerializer
