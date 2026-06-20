"""
Custom DRF permission classes for multi-tenant RBAC.
"""
from rest_framework.permissions import BasePermission

from apps.organizations.models import OrganizationMembership


class IsOrganizationMember(BasePermission):
    """
    Grants access only if the authenticated user is a member of request.organization.
    """

    message = "You are not a member of this organization."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        org = request.organization
        if org is None:
            return False
        return OrganizationMembership.objects.filter(
            user=request.user,
            organization=org,
            is_active=True,
        ).exists()


class IsOrganizationAdmin(BasePermission):
    """
    Grants access only if the authenticated user is an Admin of request.organization.
    """

    message = "You must be an organization admin to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        org = request.organization
        if org is None:
            return False
        return OrganizationMembership.objects.filter(
            user=request.user,
            organization=org,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        ).exists()


class IsOrganizationAdminOrReadOnly(BasePermission):
    """
    Read-only access for any org member; write access only for admins.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        org = request.organization
        if org is None:
            return False

        membership = OrganizationMembership.objects.filter(
            user=request.user,
            organization=org,
            is_active=True,
        ).first()

        if not membership:
            return False

        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True

        return membership.role == OrganizationMembership.Role.ADMIN


class IsSameUserOrAdmin(BasePermission):
    """
    Object-level: allows access if the requesting user owns the object
    or is an org admin.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        # Owner check
        if hasattr(obj, "user") and obj.user == request.user:
            return True
        if hasattr(obj, "assigned_to") and obj.assigned_to == request.user:
            return True

        # Admin check
        org = request.organization
        if org is None:
            return False
        return OrganizationMembership.objects.filter(
            user=request.user,
            organization=org,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        ).exists()
