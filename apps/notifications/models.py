"""
Notification system models — tenant-scoped, event-driven.
"""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.organizations.models import Organization


class Notification(BaseModel):
    """
    In-app notification for a user within an organization context.

    Notifications are created by the service layer and consumed via the API.
    The `event_type` field is used by the frontend to render the correct icon/copy.
    The `data` JSON field carries event-specific payload (task_id, commenter, etc.)
    """

    class EventType(models.TextChoices):
        # Task events
        TASK_ASSIGNED = "task_assigned", "Task Assigned"
        TASK_STATUS_CHANGED = "task_status_changed", "Task Status Changed"
        TASK_COMMENTED = "task_commented", "Task Commented"
        TASK_DUE_SOON = "task_due_soon", "Task Due Soon"
        TASK_OVERDUE = "task_overdue", "Task Overdue"
        TASK_CREATED = "task_created", "Task Created"
        TASK_DELETED = "task_deleted", "Task Deleted"
        # Org events
        MEMBER_JOINED = "member_joined", "Member Joined"
        MEMBER_REMOVED = "member_removed", "Member Removed"
        MEMBER_ROLE_CHANGED = "member_role_changed", "Member Role Changed"
        # System events
        SYSTEM_ANNOUNCEMENT = "system_announcement", "System Announcement"

    # ── Tenant isolation ────────────────────────────────────────────────────────
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )

    # ── Recipient ────────────────────────────────────────────────────────────────
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )

    # ── Content ──────────────────────────────────────────────────────────────────
    event_type = models.CharField(
        max_length=50, choices=EventType.choices, db_index=True
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    data = models.JSONField(default=dict)  # event-specific payload

    # ── State ────────────────────────────────────────────────────────────────────
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # ── Actor (who triggered the event) ──────────────────────────────────────────
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_notifications",
    )

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["organization", "recipient"]),
        ]

    def __str__(self):
        return f"[{self.event_type}] → {self.recipient.email}"

    def mark_as_read(self):
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])


class NotificationPreference(BaseModel):
    """
    Per-user, per-organization notification preferences.
    Controls which event types the user wants to receive.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )

    # Fine-grained toggles
    task_assigned = models.BooleanField(default=True)
    task_status_changed = models.BooleanField(default=True)
    task_commented = models.BooleanField(default=True)
    task_due_soon = models.BooleanField(default=True)
    task_overdue = models.BooleanField(default=True)
    member_joined = models.BooleanField(default=True)
    member_removed = models.BooleanField(default=False)
    system_announcements = models.BooleanField(default=True)

    # Delivery channels (for future use)
    in_app = models.BooleanField(default=True)
    email = models.BooleanField(default=True)

    class Meta:
        db_table = "notification_preferences"
        unique_together = ("organization", "user")
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"

    def __str__(self):
        return f"{self.user.email} prefs @ {self.organization.name}"

    def is_event_enabled(self, event_type: str) -> bool:
        """Check if a given event type is enabled for this user."""
        mapping = {
            Notification.EventType.TASK_ASSIGNED: self.task_assigned,
            Notification.EventType.TASK_STATUS_CHANGED: self.task_status_changed,
            Notification.EventType.TASK_COMMENTED: self.task_commented,
            Notification.EventType.TASK_DUE_SOON: self.task_due_soon,
            Notification.EventType.TASK_OVERDUE: self.task_overdue,
            Notification.EventType.MEMBER_JOINED: self.member_joined,
            Notification.EventType.MEMBER_REMOVED: self.member_removed,
            Notification.EventType.SYSTEM_ANNOUNCEMENT: self.system_announcements,
        }
        return mapping.get(event_type, True)
