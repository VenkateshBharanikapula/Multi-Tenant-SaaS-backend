"""
OrganizationService — all organization and membership business logic.

Responsibilities:
- Create / update / delete organizations
- List organizations for a user
- Invite, update role, remove, and leave members
- All tenant-safety checks live here (not in views)
"""
import logging
from typing import List

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceException
from apps.organizations.models import Organization, OrganizationMembership

logger = logging.getLogger(__name__)

User = get_user_model()


class OrganizationService:

    # ─── Organization CRUD ────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def create_organization(owner, validated_data: dict) -> Organization:
        """
        Create a new organization and automatically enroll the owner as Admin.
        """
        org = Organization.objects.create(
            owner=owner,
            name=validated_data["name"],
            description=validated_data.get("description", ""),
            website=validated_data.get("website", ""),
            logo=validated_data.get("logo"),
        )

        OrganizationMembership.objects.create(
            organization=org,
            user=owner,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
            joined_at=timezone.now(),
        )

        logger.info("Organization '%s' created by %s", org.name, owner.email)
        return org

    @staticmethod
    def list_user_organizations(user) -> List[Organization]:
        """Return all organizations the user is an active member of."""
        org_ids = OrganizationMembership.objects.filter(
            user=user, is_active=True
        ).values_list("organization_id", flat=True)
        return Organization.objects.filter(id__in=org_ids, is_active=True)

    @staticmethod
    def get_organization_for_user(org_id, user) -> Organization:
        """
        Fetch an organization, enforcing that the user is an active member.

        Raises:
            ServiceException(404) if org not found or user is not a member.
        """
        try:
            org = Organization.objects.get(id=org_id, is_active=True)
        except Organization.DoesNotExist:
            raise ServiceException(
                message="Organization not found.",
                code="NOT_FOUND",
                status_code=404,
            )

        is_member = OrganizationMembership.objects.filter(
            organization=org, user=user, is_active=True
        ).exists()
        if not is_member:
            raise ServiceException(
                message="Organization not found.",
                code="NOT_FOUND",
                status_code=404,
            )
        return org

    @staticmethod
    @transaction.atomic
    def update_organization(org: Organization, validated_data: dict, requesting_user) -> Organization:
        """
        Update organization metadata. Only admin can call this.
        The permission check is done at the view/permission layer,
        but we double-check here for safety.
        """
        OrganizationService._require_admin(org, requesting_user)

        for attr, value in validated_data.items():
            if value is not None:
                setattr(org, attr, value)
        org.save()
        logger.info("Organization '%s' updated by %s", org.name, requesting_user.email)
        return org

    @staticmethod
    @transaction.atomic
    def delete_organization(org_id, requesting_user) -> None:
        """
        Soft-delete an organization (set is_active=False).
        Only the owner can delete.

        Raises:
            ServiceException(403) if requesting_user is not the owner.
            ServiceException(404) if org does not exist.
        """
        try:
            org = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            raise ServiceException(
                message="Organization not found.",
                code="NOT_FOUND",
                status_code=404,
            )

        if org.owner_id != requesting_user.id:
            raise ServiceException(
                message="Only the organization owner can delete it.",
                code="FORBIDDEN",
                status_code=403,
            )

        org.is_active = False
        org.save(update_fields=["is_active", "updated_at"])
        logger.info("Organization '%s' deleted by %s", org.name, requesting_user.email)

    # ─── Membership management ────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def invite_member(organization: Organization, email: str, role: str, invited_by) -> OrganizationMembership:
        """
        Invite a user to the organization by email.
        - If the user doesn't exist, create an inactive account.
        - If the user is already a member, raise ServiceException.

        Raises:
            ServiceException(409) if user is already an active member.
        """
        OrganizationService._require_admin(organization, invited_by)

        email = email.lower().strip()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"is_active": True},
        )

        existing = OrganizationMembership.objects.filter(
            organization=organization, user=user
        ).first()

        if existing:
            if existing.is_active:
                raise ServiceException(
                    message=f"'{email}' is already a member of this organization.",
                    code="ALREADY_MEMBER",
                    status_code=409,
                )
            # Re-activate a previously removed member
            existing.is_active = True
            existing.role = role
            existing.invited_by = invited_by
            existing.joined_at = timezone.now()
            existing.save()
            membership = existing
        else:
            membership = OrganizationMembership.objects.create(
                organization=organization,
                user=user,
                role=role,
                invited_by=invited_by,
                is_active=True,
                joined_at=timezone.now(),
            )

        # Fire notification async
        from services.notification_service import NotificationService
        NotificationService.notify_member_joined(
            organization=organization,
            new_member=user,
            invited_by=invited_by,
        )

        logger.info(
            "User '%s' invited to org '%s' as %s by %s",
            email, organization.name, role, invited_by.email,
        )
        return membership

    @staticmethod
    @transaction.atomic
    def update_member_role(
        organization: Organization,
        target_user_id,
        new_role: str,
        requesting_user,
    ) -> OrganizationMembership:
        """
        Update a member's role. Prevents demoting the last admin.

        Raises:
            ServiceException(403) if requesting_user is not admin.
            ServiceException(404) if target membership not found.
            ServiceException(400) if demotion would leave org with no admins.
        """
        OrganizationService._require_admin(organization, requesting_user)

        try:
            membership = OrganizationMembership.objects.get(
                organization=organization,
                user_id=target_user_id,
                is_active=True,
            )
        except OrganizationMembership.DoesNotExist:
            raise ServiceException(
                message="Member not found in this organization.",
                code="NOT_FOUND",
                status_code=404,
            )

        # Prevent removing last admin
        if (
            membership.role == OrganizationMembership.Role.ADMIN
            and new_role != OrganizationMembership.Role.ADMIN
        ):
            admin_count = OrganizationMembership.objects.filter(
                organization=organization,
                role=OrganizationMembership.Role.ADMIN,
                is_active=True,
            ).count()
            if admin_count <= 1:
                raise ServiceException(
                    message="Cannot demote the last admin of an organization.",
                    code="LAST_ADMIN",
                    status_code=400,
                )

        old_role = membership.role
        membership.role = new_role
        membership.save(update_fields=["role", "updated_at"])

        logger.info(
            "Member '%s' role changed from %s → %s in org '%s' by %s",
            membership.user.email, old_role, new_role,
            organization.name, requesting_user.email,
        )
        return membership

    @staticmethod
    @transaction.atomic
    def remove_member(organization: Organization, target_user_id, requesting_user) -> None:
        """
        Remove (soft-deactivate) a member. Cannot remove the org owner.

        Raises:
            ServiceException(403) if requesting_user is not admin.
            ServiceException(404) if target not found.
            ServiceException(400) if trying to remove the owner.
        """
        OrganizationService._require_admin(organization, requesting_user)

        try:
            membership = OrganizationMembership.objects.get(
                organization=organization,
                user_id=target_user_id,
                is_active=True,
            )
        except OrganizationMembership.DoesNotExist:
            raise ServiceException(
                message="Member not found in this organization.",
                code="NOT_FOUND",
                status_code=404,
            )

        if organization.owner_id == membership.user_id:
            raise ServiceException(
                message="The organization owner cannot be removed.",
                code="CANNOT_REMOVE_OWNER",
                status_code=400,
            )

        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        logger.info(
            "Member '%s' removed from org '%s' by %s",
            membership.user.email, organization.name, requesting_user.email,
        )

    @staticmethod
    @transaction.atomic
    def leave_organization(organization: Organization, user) -> None:
        """
        The current user removes themselves from the organization.

        Raises:
            ServiceException(400) if the user is the owner.
            ServiceException(400) if user would leave org with no admins.
        """
        if organization.owner_id == user.id:
            raise ServiceException(
                message="Organization owners cannot leave. Transfer ownership first.",
                code="OWNER_CANNOT_LEAVE",
                status_code=400,
            )

        try:
            membership = OrganizationMembership.objects.get(
                organization=organization,
                user=user,
                is_active=True,
            )
        except OrganizationMembership.DoesNotExist:
            raise ServiceException(
                message="You are not a member of this organization.",
                code="NOT_MEMBER",
                status_code=400,
            )

        # Prevent leaving if last admin
        if membership.role == OrganizationMembership.Role.ADMIN:
            admin_count = OrganizationMembership.objects.filter(
                organization=organization,
                role=OrganizationMembership.Role.ADMIN,
                is_active=True,
            ).count()
            if admin_count <= 1:
                raise ServiceException(
                    message="You are the last admin. Assign another admin before leaving.",
                    code="LAST_ADMIN",
                    status_code=400,
                )

        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        logger.info("User '%s' left org '%s'", user.email, organization.name)

    # ─── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _require_admin(organization: Organization, user) -> None:
        """Raise ServiceException(403) if user is not an admin of the organization."""
        is_admin = OrganizationMembership.objects.filter(
            organization=organization,
            user=user,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        ).exists()
        if not is_admin:
            raise ServiceException(
                message="You must be an organization admin to perform this action.",
                code="FORBIDDEN",
                status_code=403,
            )
