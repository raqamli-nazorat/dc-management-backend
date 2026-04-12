from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import parsers, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.generics import ListCreateAPIView, UpdateAPIView
from rest_framework.permissions import AllowAny

from apps.applications.models import Region, Direction, Application
from apps.applications.serializers import (RegionSerializer, DirectionSerializer,
                                           ApplicationCreateSerializer, ApplicationStatusUpdateSerializer)
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
        if user.is_authenticated and user.role in self.admin_roles:
            return super().get_queryset()
        return super().get_queryset().filter(is_active=True)


@extend_schema(tags=['Region'])
class RegionViewSet(ActiveObjectsMixin, viewsets.ModelViewSet):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer


@extend_schema(tags=['Direction'])
class DirectionViewSet(ActiveObjectsMixin, viewsets.ModelViewSet):
    queryset = Direction.objects.all()
    serializer_class = DirectionSerializer


@extend_schema(tags=['Application'])
class ApplicationCreateView(ListCreateAPIView):
    serializer_class = ApplicationCreateSerializer
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
            'region', 'direction', 'reviewed_by'
        ).all()


@extend_schema(tags=['Application'])
class ApplicationStatusUpdateView(UpdateAPIView):
    queryset = Application.objects.all()
    serializer_class = ApplicationStatusUpdateSerializer
    permission_classes = (IsAdmin | IsManager,)
    http_method_names = ('patch',)
