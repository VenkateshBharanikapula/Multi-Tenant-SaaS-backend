"""
Organization serializers.
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.serializers import UserMinimalSerializer

from .models import Organization, OrganizationMembership

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    """Full organization representation."""

    owner = UserMinimalSerializer(read_only=True)
    member_count = serializers.IntegerField(read_only=True)
    logo_url = serializers.SerializerMethodField()
    user_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "logo_url",
            "website",
            "is_active",
            "owner",
            "member_count",
            "user_role",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "owner", "created_at", "updated_at")

    def get_logo_url(self, obj) -> str | None:
        if obj.logo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None

    def get_user_role(self, obj) -> str | None:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        membership = obj.memberships.filter(user=request.user, is_active=True).first()
        return membership.role if membership else None


class OrganizationCreateSerializer(serializers.ModelSerializer):
    """Used when creating a new organization."""

    class Meta:
        model = Organization
        fields = ("name", "description", "website", "logo")

    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Organization name must be at least 2 characters.")
        return value.strip()


class OrganizationUpdateSerializer(serializers.ModelSerializer):
    """Allows admins to update org metadata."""

    class Meta:
        model = Organization
        fields = ("name", "description", "website", "logo")


class MembershipSerializer(serializers.ModelSerializer):
    """Full membership representation."""

    user = UserMinimalSerializer(read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = (
            "id",
            "user",
            "organization_name",
            "organization_slug",
            "role",
            "is_active",
            "joined_at",
            "created_at",
        )
        read_only_fields = (
            "id", "user", "organization_name", "organization_slug",
            "joined_at", "created_at",
        )


class InviteMemberSerializer(serializers.Serializer):
    """Payload for inviting a user to an organization."""

    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=OrganizationMembership.Role.choices,
        default=OrganizationMembership.Role.MEMBER,
    )


class UpdateMemberRoleSerializer(serializers.Serializer):
    """Payload for changing a member's role."""

    role = serializers.ChoiceField(choices=OrganizationMembership.Role.choices)


class RemoveMemberSerializer(serializers.Serializer):
    """Payload for removing a member from an organization."""

    user_id = serializers.UUIDField()
