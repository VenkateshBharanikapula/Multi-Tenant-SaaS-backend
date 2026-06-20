"""
NotificationService — event-driven notification creation and delivery.

Architecture:
  - Synchronous path: creates Notification DB records directly (always safe).
  - Async path: dispatches Celery tasks for email delivery and bulk operations.

All public methods are safe to call from within a DB transaction
(they enqueue Celery tasks rather than doing I/O inside the transaction).
"""
import logging
from typing import List, Optional

from django.db.models import QuerySet
from django.utils import timezone

from apps.notifications.models import Notification, NotificationPreference
from apps.organizations.models import Organization, OrganizationMembership

logger = logging.getLogger(__name__)


class NotificationService:

    # ─── Query helpers ────────────────────────────────────────────────────────

    @staticmethod
    def get_user_notifications(
        user,
        organization: Organization,
        unread_only: bool = False,
    ) -> QuerySet:
        qs = Notification.objects.filter(
            recipient=user,
            organization=organization,
        ).select_related("actor")
        if unread_only:
            qs = qs.filter(is_read=False)
        return qs

    @staticmethod
    def get_stats(user, organization: Organization) -> dict:
        qs = Notification.objects.filter(recipient=user, organization=organization)
        total = qs.count()
        unread = qs.filter(is_read=False).count()
        return {"total": total, "unread": unread, "read": total - unread}

    @staticmethod
    def get_or_create_preferences(user, organization: Organization) -> NotificationPreference:
        prefs, _ = NotificationPreference.objects.get_or_create(
            user=user,
            organization=organization,
        )
        return prefs

    # ─── Read / delete management ─────────────────────────────────────────────

    @staticmethod
    def mark_read(
        user,
        organization: Organization,
        notification_ids: Optional[List] = None,
    ) -> int:
        """
        Mark notifications as read.
        If notification_ids is None/empty, marks ALL unread notifications for the user.
        Returns the count of notifications marked as read.
        """
        qs = Notification.objects.filter(
            recipient=user,
            organization=organization,
            is_read=False,
        )
        if notification_ids:
            qs = qs.filter(id__in=notification_ids)

        count = qs.count()
        qs.update(is_read=True, read_at=timezone.now())
        return count

    @staticmethod
    def delete_read_notifications(user, organization: Organization) -> None:
        Notification.objects.filter(
            recipient=user,
            organization=organization,
            is_read=True,
        ).delete()

    # ─── Event emitters ───────────────────────────────────────────────────────

    @staticmethod
    def notify_task_assigned(task, assignee, assigned_by) -> None:
        """Create a TASK_ASSIGNED notification for the assignee."""
        NotificationService._create(
            organization=task.organization,
            recipient=assignee,
            actor=assigned_by,
            event_type=Notification.EventType.TASK_ASSIGNED,
            title="Task assigned to you",
            body=f"'{assigned_by.full_name}' assigned you the task: \"{task.title}\"",
            data={
                "task_id": str(task.id),
                "task_title": task.title,
                "assigned_by_id": str(assigned_by.id),
            },
        )

    @staticmethod
    def notify_task_status_changed(task, old_status: str, new_status: str, changed_by) -> None:
        """
        Notify the task creator and assignee (if different from changer)
        about a status change.
        """
        recipients = set()
        if task.created_by and task.created_by != changed_by:
            recipients.add(task.created_by)
        if task.assigned_to and task.assigned_to != changed_by:
            recipients.add(task.assigned_to)

        for recipient in recipients:
            NotificationService._create(
                organization=task.organization,
                recipient=recipient,
                actor=changed_by,
                event_type=Notification.EventType.TASK_STATUS_CHANGED,
                title=f"Task status updated: {task.title}",
                body=f"Status changed from '{old_status}' to '{new_status}' by {changed_by.full_name}.",
                data={
                    "task_id": str(task.id),
                    "task_title": task.title,
                    "from_status": old_status,
                    "to_status": new_status,
                },
            )

    @staticmethod
    def notify_task_commented(task, comment, commenter) -> None:
        """
        Notify the task creator and assignee about a new comment,
        excluding the commenter themselves.
        """
        recipients = set()
        if task.created_by and task.created_by != commenter:
            recipients.add(task.created_by)
        if task.assigned_to and task.assigned_to != commenter:
            recipients.add(task.assigned_to)

        for recipient in recipients:
            NotificationService._create(
                organization=task.organization,
                recipient=recipient,
                actor=commenter,
                event_type=Notification.EventType.TASK_COMMENTED,
                title=f"New comment on: {task.title}",
                body=f"{commenter.full_name} commented: \"{comment.body[:100]}\"",
                data={
                    "task_id": str(task.id),
                    "task_title": task.title,
                    "comment_id": str(comment.id),
                },
            )

    @staticmethod
    def notify_member_joined(organization: Organization, new_member, invited_by) -> None:
        """
        Notify all org admins that a new member joined.
        """
        admin_ids = OrganizationMembership.objects.filter(
            organization=organization,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        ).exclude(user=invited_by).values_list("user_id", flat=True)

        from django.contrib.auth import get_user_model
        User = get_user_model()
        admins = User.objects.filter(id__in=admin_ids)

        for admin in admins:
            NotificationService._create(
                organization=organization,
                recipient=admin,
                actor=new_member,
                event_type=Notification.EventType.MEMBER_JOINED,
                title="New member joined",
                body=f"{new_member.full_name} ({new_member.email}) joined {organization.name}.",
                data={
                    "user_id": str(new_member.id),
                    "user_email": new_member.email,
                    "invited_by_id": str(invited_by.id),
                },
            )

    @staticmethod
    def notify_member_removed(organization: Organization, removed_user, removed_by) -> None:
        """Notify the removed user."""
        NotificationService._create(
            organization=organization,
            recipient=removed_user,
            actor=removed_by,
            event_type=Notification.EventType.MEMBER_REMOVED,
            title="You have been removed from an organization",
            body=f"You have been removed from '{organization.name}' by {removed_by.full_name}.",
            data={
                "organization_id": str(organization.id),
                "organization_name": organization.name,
            },
        )

    @staticmethod
    def send_system_announcement(organization: Organization, title: str, body: str) -> int:
        """
        Send a system-wide notification to ALL active members of an organization.
        Returns the number of notifications created.
        This uses a Celery task for bulk delivery.
        """
        from apps.notifications.tasks import send_bulk_notification_task
        send_bulk_notification_task.delay(
            organization_id=str(organization.id),
            event_type=Notification.EventType.SYSTEM_ANNOUNCEMENT,
            title=title,
            body=body,
            data={},
        )
        member_count = OrganizationMembership.objects.filter(
            organization=organization, is_active=True
        ).count()
        return member_count

    # ─── Internal factory ────────────────────────────────────────────────────

    @staticmethod
    def _create(
        organization: Organization,
        recipient,
        actor,
        event_type: str,
        title: str,
        body: str = "",
        data: dict = None,
    ) -> Optional[Notification]:
        """
        Internal notification creation.
        Checks user's notification preferences before creating.
        Dispatches async email if the channel is enabled.
        """
        # Check preferences (get_or_create ensures a record exists)
        prefs, _ = NotificationPreference.objects.get_or_create(
            user=recipient,
            organization=organization,
        )

        if not prefs.is_event_enabled(event_type):
            logger.debug(
                "Notification suppressed for %s (event=%s, pref disabled)",
                recipient.email, event_type,
            )
            return None

        if not prefs.in_app:
            return None

        notification = Notification.objects.create(
            organization=organization,
            recipient=recipient,
            actor=actor,
            event_type=event_type,
            title=title,
            body=body,
            data=data or {},
        )

        # Dispatch email notification asynchronously if enabled
        if prefs.email:
            from apps.notifications.tasks import send_email_notification_task
            send_email_notification_task.delay(str(notification.id))

        return notification
