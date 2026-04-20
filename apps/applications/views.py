from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import parsers, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny

from apps.applications.models import Region, District, Direction, Application
from apps.applications.serializers import (RegionSerializer, DistrictSerializer, DirectionSerializer,
                                           ApplicationSerializer, ApplicationStatusUpdateSerializer)
from apps.users.permissions import IsAdmin, IsManager, IsSuperAdmin
from apps.users.models import Role


class ActiveObjectsMixin:
    admin_roles = [Role.SUPERADMIN, Role.ADMIN, Role.MANAGER]

    def get_permissions(self):
        if self.action == 'list':
            return [AllowAny()]
        return [(IsSuperAdmin | IsAdmin | IsManager)()]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.has_role(*self.admin_roles):
            return super().get_queryset()
        return super().get_queryset().filter(is_application=True, is_active=True)


class RegionViewSet(ActiveObjectsMixin, viewsets.ModelViewSet):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer


@extend_schema(tags=['District'])
class DistrictViewSet(ActiveObjectsMixin, viewsets.ModelViewSet):
    queryset = District.objects.select_related('region').all()
    serializer_class = DistrictSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['region']


@extend_schema(tags=['Direction'])
class DirectionViewSet(ActiveObjectsMixin, viewsets.ModelViewSet):
    queryset = Direction.objects.all()
    serializer_class = DirectionSerializer


@extend_schema(tags=['Application'])
class ApplicationView(ListCreateAPIView):
    serializer_class = ApplicationSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    permission_classes = (AllowAny,)
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status']
    search_fields = ['full_name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [AllowAny()]
        return [(IsAdmin | IsManager)()]

    def get_queryset(self):
        return Application.objects.select_related(
            'region', 'district', 'direction', 'reviewed_by'
        ).all()


@extend_schema(tags=['Application'])
class ApplicationDetailView(RetrieveUpdateAPIView):
    queryset = Application.objects.select_related(
        'region', 'district', 'direction', 'reviewed_by'
    ).all()
    permission_classes = (IsAdmin | IsManager,)
    http_method_names = ('get', 'patch',)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return ApplicationSerializer
        return ApplicationStatusUpdateSerializer
