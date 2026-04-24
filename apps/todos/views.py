from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, permissions, filters

from .serializers import TodoSerializer
from .models import Todo

from apps.common.mixins import SoftDeleteMixin

@extend_schema(tags=['Todo'])
class TodoViewSet(SoftDeleteMixin, viewsets.ModelViewSet):
    queryset = Todo.objects.filter(is_active=True)
    serializer_class = TodoSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_done']
    search_fields = ['title']
    ordering_fields = ['created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(user=self.request.user).select_related('user')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
