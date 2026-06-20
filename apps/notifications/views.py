"""
Notification views.
"""
import logging

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.exceptions import ServiceException
from apps.core.permissions import IsOrganizationMember
from services.notification_service import NotificationService

from .serializers import (
    MarkReadSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
    NotificationStatsSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema(tags=["Notifications"])
@extend_schema_view(
    list=extend_schema(summary="List notifications for the current user in the current org"),
)
class NotificationViewSet(GenericViewSet):
    """
    Manages notifications for the authenticated user within the current organization.
    """

    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def list(self, request):
        """List notifications — supports ?unread=true filter."""
        unread_only = request.query_params.get("unread", "").lower() == "true"
        notifications = NotificationService.get_user_notifications(
            user=request.user,
            organization=request.organization,
            unread_only=unread_only,
        )
        page = self.paginate_queryset(notifications)
        if page is not None:
            return self.get_paginated_response(
                NotificationSerializer(page, many=True).data
            )
        return Response(NotificationSerializer(notifications, many=True).data)

    @extend_schema(
        responses={200: NotificationStatsSerializer},
        summary="Get notification counts (total / unread / read)",
    )
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        data = NotificationService.get_stats(
            user=request.user,
            organization=request.organization,
        )
        return Response(NotificationStatsSerializer(data).data)

    @extend_schema(
        request=MarkReadSerializer,
        responses={200: {"type": "object", "properties": {"marked": {"type": "integer"}}}},
        summary="Mark notifications as read",
    )
    @action(detail=False, methods=["post"], url_path="mark-read")
    def mark_read(self, request):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notification_ids = serializer.validated_data.get("notification_ids")
        try:
            count = NotificationService.mark_read(
                user=request.user,
                organization=request.organization,
                notification_ids=notification_ids,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response({"marked": count})

    @extend_schema(
        responses={204: None},
        summary="Delete all read notifications",
    )
    @action(detail=False, methods=["delete"], url_path="clear-read")
    def clear_read(self, request):
        NotificationService.delete_read_notifications(
            user=request.user,
            organization=request.organization,
        )
        from rest_framework import status
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Notifications"])
class NotificationPreferenceViewSet(GenericViewSet):
    """
    Manage per-user notification preferences within an organization.
    """

    permission_classes = [IsAuthenticated, IsOrganizationMember]

    @extend_schema(
        responses={200: NotificationPreferenceSerializer},
        summary="Get notification preferences",
    )
    @action(detail=False, methods=["get"], url_path="preferences")
    def get_preferences(self, request):
        prefs = NotificationService.get_or_create_preferences(
            user=request.user,
            organization=request.organization,
        )
        return Response(NotificationPreferenceSerializer(prefs).data)

    @extend_schema(
        request=NotificationPreferenceSerializer,
        responses={200: NotificationPreferenceSerializer},
        summary="Update notification preferences",
    )
    @action(detail=False, methods=["patch"], url_path="preferences/update")
    def update_preferences(self, request):
        prefs = NotificationService.get_or_create_preferences(
            user=request.user,
            organization=request.organization,
        )
        serializer = NotificationPreferenceSerializer(
            prefs, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
