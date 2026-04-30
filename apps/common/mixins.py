from rest_framework import status
from rest_framework.response import Response


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
