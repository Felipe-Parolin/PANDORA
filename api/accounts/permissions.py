from rest_framework.permissions import BasePermission
from rest_framework.permissions import SAFE_METHODS

from .models import User


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and (request.user.is_superuser or request.user.role == User.Role.ADMIN))


class RolePermission(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and (request.user.is_superuser or request.user.role in self.allowed_roles))


class IsAdminOrSales(RolePermission):
    allowed_roles = (User.Role.ADMIN, User.Role.SALES)


class IsAdminOrMaintenance(RolePermission):
    allowed_roles = (User.Role.ADMIN, User.Role.MAINTENANCE)


class ACLPermission(BasePermission):
    message = "Seu grupo não possui permissão para esta operação."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        permission = getattr(view, "acl_view", None) if request.method in SAFE_METHODS else getattr(view, "acl_manage", None)
        if not permission:
            return True
        if isinstance(permission, (tuple, list, set)):
            return any(request.user.has_acl(item) for item in permission)
        return request.user.has_acl(permission)
