from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status


class SoftDeleteMixin:
    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoleBasedQuerySetMixin:
    full_access_roles = []

    def get_role_based_queryset(self, queryset, user):
        return queryset

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()

        if not user or not user.is_authenticated:
            return queryset.none()

        if user.is_superuser or (self.full_access_roles and user.has_role(*self.full_access_roles)):
            return queryset

        return self.get_role_based_queryset(queryset, user)


class TrashMixin:
    @extend_schema(request=None)
    @action(detail=False, methods=['get'])
    def trash(self, request):
        queryset = self.filter_queryset(self.get_queryset()).filter(created_by=request.user)
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(request=None)
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        instance = self.get_queryset().filter(pk=pk, created_by=request.user).first()

        if not instance:
            return Response({"detail": "Ma'lumot topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, instance)

        if not getattr(instance, 'is_deleted', False):
            return Response({"detail": "Element chiqindi qutisida emas."}, status=status.HTTP_400_BAD_REQUEST)

        instance.is_active = True
        instance.is_deleted = False
        instance.save()

        return Response({"detail": "Muvaffaqiyatli tiklandi."})

    @action(detail=True, methods=['delete'])
    def hard_delete(self, request, pk=None):
        instance = self.get_queryset().filter(pk=pk, created_by=request.user).first()

        if not instance:
            return Response({"detail": "Ma'lumot topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, instance)

        if not getattr(instance, 'is_deleted', False):
            return Response({"detail": "Faqat chiqindi qutisidagi elementlarni butunlay o'chirish mumkin."},
                            status=status.HTTP_400_BAD_REQUEST)

        instance.is_deleted = False
        instance.is_active = False
        instance.save()

        return Response(status=status.HTTP_204_NO_CONTENT)
