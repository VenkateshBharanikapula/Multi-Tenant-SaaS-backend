"""
Organization views — thin layer delegating to OrganizationService.
"""
import logging

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.exceptions import ServiceException
from apps.core.permissions import IsOrganizationAdmin, IsOrganizationMember
from services.organization_service import OrganizationService

from .models import Organization, OrganizationMembership
from .serializers import (
    InviteMemberSerializer,
    MembershipSerializer,
    OrganizationCreateSerializer,
    OrganizationSerializer,
    OrganizationUpdateSerializer,
    UpdateMemberRoleSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema(tags=["Organizations"])
@extend_schema_view(
    list=extend_schema(summary="List my organizations"),
    create=extend_schema(summary="Create a new organization"),
    retrieve=extend_schema(summary="Get organization details"),
    update=extend_schema(summary="Update organization"),
    partial_update=extend_schema(summary="Partially update organization"),
    destroy=extend_schema(summary="Delete organization"),
)
class OrganizationViewSet(GenericViewSet):
    """CRUD for organizations. Users see only their own orgs."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return OrganizationCreateSerializer
        if self.action in ("update", "partial_update"):
            return OrganizationUpdateSerializer
        return OrganizationSerializer

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsOrganizationAdmin()]
        return [IsAuthenticated()]

    def list(self, request):
        """List all organizations the user is an active member of."""
        orgs = OrganizationService.list_user_organizations(user=request.user)
        serializer = OrganizationSerializer(orgs, many=True, context={"request": request})
        return Response(serializer.data)

    def create(self, request):
        """Create a new organization; caller becomes owner + admin."""
        serializer = OrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            org = OrganizationService.create_organization(
                owner=request.user,
                validated_data=serializer.validated_data,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(
            OrganizationSerializer(org, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        """Get details of a single organization (member-only)."""
        try:
            org = OrganizationService.get_organization_for_user(
                org_id=pk, user=request.user
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(OrganizationSerializer(org, context={"request": request}).data)

    def update(self, request, pk=None):
        return self._update(request, pk, partial=False)

    def partial_update(self, request, pk=None):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, partial):
        try:
            org = OrganizationService.get_organization_for_user(
                org_id=pk, user=request.user
            )
            serializer = OrganizationUpdateSerializer(org, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            updated = OrganizationService.update_organization(
                org=org,
                validated_data=serializer.validated_data,
                requesting_user=request.user,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(OrganizationSerializer(updated, context={"request": request}).data)

    def destroy(self, request, pk=None):
        try:
            OrganizationService.delete_organization(org_id=pk, requesting_user=request.user)
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Members"])
class MembershipViewSet(GenericViewSet):
    """
    Manage organization members.
    All endpoints operate on request.organization (resolved by TenantMiddleware).
    """

    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def list(self, request):
        """List all active members of the current organization."""
        org = request.organization
        memberships = (
            OrganizationMembership.objects.filter(organization=org, is_active=True)
            .select_related("user")
            .order_by("user__first_name")
        )
        serializer = MembershipSerializer(memberships, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=InviteMemberSerializer,
        responses={201: MembershipSerializer},
        summary="Invite a user to the organization",
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="invite",
        permission_classes=[IsAuthenticated, IsOrganizationAdmin],
    )
    def invite(self, request):
        """Invite a user by email. Creates user if they don't exist."""
        serializer = InviteMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            membership = OrganizationService.invite_member(
                organization=request.organization,
                email=serializer.validated_data["email"],
                role=serializer.validated_data["role"],
                invited_by=request.user,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(
            MembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=UpdateMemberRoleSerializer,
        responses={200: MembershipSerializer},
        summary="Update a member's role",
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path="role",
        permission_classes=[IsAuthenticated, IsOrganizationAdmin],
    )
    def update_role(self, request, pk=None):
        serializer = UpdateMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            membership = OrganizationService.update_member_role(
                organization=request.organization,
                target_user_id=pk,
                new_role=serializer.validated_data["role"],
                requesting_user=request.user,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(MembershipSerializer(membership).data)

    @extend_schema(summary="Remove a member from the organization")
    @action(
        detail=True,
        methods=["delete"],
        url_path="remove",
        permission_classes=[IsAuthenticated, IsOrganizationAdmin],
    )
    def remove(self, request, pk=None):
        try:
            OrganizationService.remove_member(
                organization=request.organization,
                target_user_id=pk,
                requesting_user=request.user,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(summary="Leave the organization")
    @action(detail=False, methods=["post"], url_path="leave")
    def leave(self, request):
        try:
            OrganizationService.leave_organization(
                organization=request.organization,
                user=request.user,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
