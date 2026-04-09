from rest_framework import permissions
from apps.users.models import Role


class RoleBasePermission(permissions.BasePermission):
    required_roles = []

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if user.role == Role.SUPERADMIN or user.is_superuser:
            return True

        return user.role in self.required_roles


class IsSuperAdmin(RoleBasePermission):
    required_roles = [Role.SUPERADMIN]


class IsAdmin(RoleBasePermission):
    required_roles = [Role.ADMIN]


class IsManager(RoleBasePermission):
    required_roles = [Role.MANAGER]


class IsEmployee(RoleBasePermission):
    required_roles = [Role.EMPLOYEE]


class IsAuditor(RoleBasePermission):
    required_roles = [Role.AUDITOR]


class IsAccountant(RoleBasePermission):
    required_roles = [Role.ACCOUNTANT]


class IsAdminOrManager(RoleBasePermission):
    required_roles = [Role.ADMIN, Role.MANAGER]
