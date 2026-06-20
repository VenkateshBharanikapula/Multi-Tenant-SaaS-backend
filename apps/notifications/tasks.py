"""
Celery tasks for the notifications app.

All tasks use bind=True so they can retry on failure.
Task names are explicit to avoid issues with app renaming.
"""
import logging

from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="notifications.send_email_notification",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
)
def send_email_notification_task(self, notification_id: str) -> dict:
    """
    Send an email for a specific Notification record.
    Retries up to 3 times with a 60-second delay on failure.
    """
    from apps.notifications.models import Notification

    try:
        notification = Notification.objects.select_related(
            "recipient", "actor", "organization"
        ).get(id=notification_id)
    except Notification.DoesNotExist:
        logger.warning("Notification %s not found, skipping email.", notification_id)
        return {"status": "skipped", "reason": "not_found"}

    recipient_email = notification.recipient.email
    subject = f"[{notification.organization.name}] {notification.title}"
    message = notification.body or notification.title

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        logger.info(
            "Email notification sent to %s (notification=%s)",
            recipient_email, notification_id,
        )
        return {"status": "sent", "recipient": recipient_email}
    except Exception as exc:
        logger.exception(
            "Failed to send email notification %s to %s",
            notification_id, recipient_email,
        )
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="notifications.send_bulk_notification",
    max_retries=2,
    default_retry_delay=120,
)
def send_bulk_notification_task(
    self,
    organization_id: str,
    event_type: str,
    title: str,
    body: str,
    data: dict,
    actor_id: str = None,
) -> dict:
    """
    Create in-app notifications for ALL active members of an organization.
    Used for system-wide announcements.
    """
    from apps.notifications.models import Notification, NotificationPreference
    from apps.organizations.models import Organization, OrganizationMembership

    try:
        organization = Organization.objects.get(id=organization_id)
    except Organization.DoesNotExist:
        logger.warning("Organization %s not found, skipping bulk notification.", organization_id)
        return {"status": "skipped", "reason": "org_not_found"}

    actor = None
    if actor_id:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        actor = User.objects.filter(id=actor_id).first()

    memberships = OrganizationMembership.objects.filter(
        organization=organization, is_active=True
    ).select_related("user")

    created_count = 0
    for membership in memberships:
        recipient = membership.user

        prefs, _ = NotificationPreference.objects.get_or_create(
            user=recipient,
            organization=organization,
        )
        if not prefs.in_app or not prefs.is_event_enabled(event_type):
            continue

        Notification.objects.create(
            organization=organization,
            recipient=recipient,
            actor=actor,
            event_type=event_type,
            title=title,
            body=body,
            data=data,
        )
        created_count += 1

    logger.info(
        "Bulk notification '%s' sent to %d members of org '%s'",
        title, created_count, organization.name,
    )
    return {"status": "ok", "created": created_count}


@shared_task(
    name="notifications.cleanup_old_notifications",
    ignore_result=True,
)
def cleanup_old_notifications_task(days: int = 90) -> dict:
    """
    Periodic task: delete read notifications older than `days` days.
    Scheduled via django-celery-beat in the admin or via CELERY_BEAT_SCHEDULE.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.notifications.models import Notification

    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = Notification.objects.filter(
        is_read=True,
        created_at__lt=cutoff,
    ).delete()

    logger.info("Cleaned up %d old notifications (older than %d days).", deleted, days)
    return {"deleted": deleted}


@shared_task(
    name="notifications.send_overdue_task_notifications",
    ignore_result=True,
)
def send_overdue_task_notifications_task() -> dict:
    """
    Periodic task: notify assignees of overdue tasks.
    Should be scheduled to run every few hours via django-celery-beat.
    """
    from django.utils import timezone

    from apps.notifications.models import Notification
    from apps.tasks.models import Task

    now = timezone.now()
    overdue_tasks = (
        Task.objects.filter(
            due_date__lt=now,
            assigned_to__isnull=False,
        )
        .exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED])
        .select_related("assigned_to", "organization", "created_by")
    )

    notified_count = 0
    for task in overdue_tasks:
        # Avoid spamming — only notify once per day
        already_notified_today = Notification.objects.filter(
            task_id=task.id if hasattr(Notification, "task_id") else None,
            recipient=task.assigned_to,
            event_type=Notification.EventType.TASK_OVERDUE,
            created_at__date=now.date(),
        ).exists() if hasattr(Notification, "task_id") else False

        if not already_notified_today:
            from services.notification_service import NotificationService
            NotificationService._create(
                organization=task.organization,
                recipient=task.assigned_to,
                actor=None,
                event_type=Notification.EventType.TASK_OVERDUE,
                title=f"Overdue task: {task.title}",
                body=f"Your task \"{task.title}\" was due {task.due_date.strftime('%b %d, %Y')} and is still open.",
                data={"task_id": str(task.id), "due_date": task.due_date.isoformat()},
            )
            notified_count += 1

    logger.info("Sent %d overdue task notifications.", notified_count)
    return {"notified": notified_count}
