from rest_framework.permissions import BasePermission

from accounts.models import PlatformAdmin


def is_platform_admin(user):
    return user.is_authenticated and PlatformAdmin.objects.filter(user=user).exists()


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_platform_admin(request.user)
