"""
Notification serializers.
"""
from rest_framework import serializers

from apps.users.serializers import UserMinimalSerializer

from .models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    actor = UserMinimalSerializer(read_only=True)
    event_type_display = serializers.CharField(
        source="get_event_type_display", read_only=True
    )

    class Meta:
        model = Notification
        fields = (
            "id",
            "event_type",
            "event_type_display",
            "title",
            "body",
            "data",
            "is_read",
            "read_at",
            "actor",
            "created_at",
        )
        read_only_fields = fields


class MarkReadSerializer(serializers.Serializer):
    """Payload for marking specific notifications as read."""

    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="List of notification IDs to mark as read. Omit to mark ALL as read.",
    )


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = (
            "id",
            "task_assigned",
            "task_status_changed",
            "task_commented",
            "task_due_soon",
            "task_overdue",
            "member_joined",
            "member_removed",
            "system_announcements",
            "in_app",
            "email",
            "updated_at",
        )
        read_only_fields = ("id", "updated_at")


class NotificationStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    unread = serializers.IntegerField()
    read = serializers.IntegerField()
