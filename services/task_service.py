"""
TaskService — all task management business logic.

Responsibilities:
- Full task CRUD
- Status transitions with activity logging
- Assignment management
- Comment management
- Tag management
- Statistics
"""
import logging
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, QuerySet
from django.utils import timezone

from apps.core.exceptions import ServiceException
from apps.organizations.models import Organization, OrganizationMembership
from apps.tasks.models import Task, TaskActivity, TaskComment, TaskTag

logger = logging.getLogger(__name__)

User = get_user_model()


class TaskService:

    # ─── Task CRUD ─────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def create_task(organization: Organization, created_by, validated_data: dict) -> Task:
        """
        Create a new task within an organization.
        Validates the assignee belongs to the same organization.
        """
        assignee = None
        assignee_id = validated_data.pop("assigned_to_id", None)
        if assignee_id:
            assignee = TaskService._get_org_member_user(organization, assignee_id)

        parent = None
        parent_id = validated_data.pop("parent_id", None)
        if parent_id:
            parent = TaskService._get_task(parent_id, organization)

        tag_ids = validated_data.pop("tag_ids", [])

        task = Task.objects.create(
            organization=organization,
            created_by=created_by,
            assigned_to=assignee,
            parent=parent,
            **validated_data,
        )

        if tag_ids:
            tags = TaskTag.objects.filter(id__in=tag_ids, organization=organization)
            task.tags.set(tags)

        TaskActivity.objects.create(
            organization=organization,
            task=task,
            actor=created_by,
            activity_type=TaskActivity.ActivityType.CREATED,
            metadata={"title": task.title},
        )

        # Notify assignee if set
        if assignee and assignee != created_by:
            from services.notification_service import NotificationService
            NotificationService.notify_task_assigned(
                task=task,
                assignee=assignee,
                assigned_by=created_by,
            )

        logger.info("Task '%s' created in org '%s' by %s", task.title, organization.slug, created_by.email)
        return task

    @staticmethod
    def get_task(task_id, organization: Organization) -> Task:
        """
        Fetch a single task by ID, scoped to the organization.

        Raises:
            ServiceException(404) if not found.
        """
        try:
            return (
                Task.objects.filter(organization=organization)
                .select_related("assigned_to", "created_by", "parent", "organization")
                .prefetch_related("tags", "comments__author", "activities__actor")
                .get(id=task_id)
            )
        except Task.DoesNotExist:
            raise ServiceException(
                message="Task not found.",
                code="NOT_FOUND",
                status_code=404,
            )

    @staticmethod
    @transaction.atomic
    def update_task(task_id, organization: Organization, updated_by, validated_data: dict) -> Task:
        """
        Update task fields. Validates assignee belongs to the same org.
        Logs an activity entry for the update.
        """
        task = TaskService.get_task(task_id, organization)

        assignee_id = validated_data.pop("assigned_to_id", ...)
        tag_ids = validated_data.pop("tag_ids", None)

        changes = {}
        for attr, value in validated_data.items():
            old_value = getattr(task, attr)
            if old_value != value:
                changes[attr] = {"from": str(old_value), "to": str(value)}
            setattr(task, attr, value)

        if assignee_id is not ...:
            new_assignee = None
            if assignee_id:
                new_assignee = TaskService._get_org_member_user(organization, assignee_id)
            if task.assigned_to != new_assignee:
                changes["assigned_to"] = {
                    "from": task.assigned_to.email if task.assigned_to else None,
                    "to": new_assignee.email if new_assignee else None,
                }
            task.assigned_to = new_assignee

        # Mark completed_at when status moves to DONE
        if validated_data.get("status") == Task.Status.DONE and not task.completed_at:
            task.completed_at = timezone.now()
        elif validated_data.get("status") and validated_data["status"] != Task.Status.DONE:
            task.completed_at = None

        task.save()

        if tag_ids is not None:
            tags = TaskTag.objects.filter(id__in=tag_ids, organization=organization)
            task.tags.set(tags)

        if changes:
            TaskActivity.objects.create(
                organization=organization,
                task=task,
                actor=updated_by,
                activity_type=TaskActivity.ActivityType.UPDATED,
                metadata={"changes": changes},
            )

        logger.debug("Task '%s' updated by %s", task.title, updated_by.email)
        return task

    @staticmethod
    @transaction.atomic
    def update_task_status(
        task_id,
        organization: Organization,
        new_status: str,
        updated_by,
    ) -> Task:
        """
        Targeted status update with activity logging and notifications.
        """
        task = TaskService.get_task(task_id, organization)
        old_status = task.status

        if old_status == new_status:
            return task

        task.status = new_status
        if new_status == Task.Status.DONE:
            task.completed_at = timezone.now()
        elif old_status == Task.Status.DONE:
            task.completed_at = None
        task.save(update_fields=["status", "completed_at", "updated_at"])

        TaskActivity.objects.create(
            organization=organization,
            task=task,
            actor=updated_by,
            activity_type=TaskActivity.ActivityType.STATUS_CHANGED,
            metadata={"from": old_status, "to": new_status},
        )

        # Notify relevant users
        from services.notification_service import NotificationService
        NotificationService.notify_task_status_changed(
            task=task,
            old_status=old_status,
            new_status=new_status,
            changed_by=updated_by,
        )

        logger.info(
            "Task '%s' status: %s → %s by %s",
            task.title, old_status, new_status, updated_by.email,
        )
        return task

    @staticmethod
    @transaction.atomic
    def assign_task(
        task_id,
        organization: Organization,
        assignee_id: Optional[str],
        assigned_by,
    ) -> Task:
        """
        Assign or unassign a task. Validates the assignee is an org member.
        """
        task = TaskService.get_task(task_id, organization)
        old_assignee = task.assigned_to

        new_assignee = None
        if assignee_id:
            new_assignee = TaskService._get_org_member_user(organization, assignee_id)

        task.assigned_to = new_assignee
        task.save(update_fields=["assigned_to", "updated_at"])

        activity_type = (
            TaskActivity.ActivityType.ASSIGNED
            if new_assignee
            else TaskActivity.ActivityType.UNASSIGNED
        )
        TaskActivity.objects.create(
            organization=organization,
            task=task,
            actor=assigned_by,
            activity_type=activity_type,
            metadata={
                "from": old_assignee.email if old_assignee else None,
                "to": new_assignee.email if new_assignee else None,
            },
        )

        if new_assignee and new_assignee != assigned_by:
            from services.notification_service import NotificationService
            NotificationService.notify_task_assigned(
                task=task,
                assignee=new_assignee,
                assigned_by=assigned_by,
            )

        return task

    @staticmethod
    @transaction.atomic
    def delete_task(task_id, organization: Organization, deleted_by) -> None:
        """
        Hard-delete a task. Logs activity before deletion.
        """
        task = TaskService.get_task(task_id, organization)
        title = task.title

        # Log before delete so the activity record exists
        TaskActivity.objects.create(
            organization=organization,
            task=task,
            actor=deleted_by,
            activity_type=TaskActivity.ActivityType.DELETED,
            metadata={"title": title},
        )

        task.delete()
        logger.info("Task '%s' deleted by %s in org '%s'", title, deleted_by.email, organization.slug)

    # ─── Comments ─────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def add_comment(task_id, organization: Organization, author, body: str) -> TaskComment:
        task = TaskService.get_task(task_id, organization)

        comment = TaskComment.objects.create(
            organization=organization,
            task=task,
            author=author,
            body=body,
        )

        TaskActivity.objects.create(
            organization=organization,
            task=task,
            actor=author,
            activity_type=TaskActivity.ActivityType.COMMENTED,
            metadata={"comment_id": str(comment.id)},
        )

        # Notify task creator and assignee (excluding the commenter)
        from services.notification_service import NotificationService
        NotificationService.notify_task_commented(
            task=task,
            comment=comment,
            commenter=author,
        )

        return comment

    @staticmethod
    def get_task_comments(task_id, organization: Organization) -> QuerySet:
        task = TaskService.get_task(task_id, organization)
        return task.comments.select_related("author").order_by("created_at")

    # ─── Tags ─────────────────────────────────────────────────────────────────

    @staticmethod
    def create_tag(organization: Organization, validated_data: dict) -> TaskTag:
        name = validated_data["name"].strip().lower()
        if TaskTag.objects.filter(organization=organization, name=name).exists():
            raise ServiceException(
                message=f"Tag '{name}' already exists in this organization.",
                code="TAG_EXISTS",
                status_code=409,
            )
        return TaskTag.objects.create(
            organization=organization,
            name=name,
            color=validated_data.get("color", "#3B82F6"),
        )

    @staticmethod
    def delete_tag(tag_id, organization: Organization, requesting_user) -> None:
        try:
            tag = TaskTag.objects.get(id=tag_id, organization=organization)
        except TaskTag.DoesNotExist:
            raise ServiceException(
                message="Tag not found.",
                code="NOT_FOUND",
                status_code=404,
            )
        tag.delete()

    # ─── Statistics ───────────────────────────────────────────────────────────

    @staticmethod
    def get_task_stats(organization: Organization) -> dict:
        """Returns a summary of task counts grouped by status and priority."""
        qs = Task.objects.filter(organization=organization)
        now = timezone.now()

        status_counts = dict(
            qs.values_list("status").annotate(count=Count("id")).values_list("status", "count")
        )
        priority_counts = dict(
            qs.values_list("priority").annotate(count=Count("id")).values_list("priority", "count")
        )
        overdue_count = qs.filter(
            due_date__lt=now
        ).exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED]).count()

        return {
            "total": qs.count(),
            "by_status": {
                "todo": status_counts.get(Task.Status.TODO, 0),
                "in_progress": status_counts.get(Task.Status.IN_PROGRESS, 0),
                "in_review": status_counts.get(Task.Status.IN_REVIEW, 0),
                "done": status_counts.get(Task.Status.DONE, 0),
                "cancelled": status_counts.get(Task.Status.CANCELLED, 0),
            },
            "by_priority": {
                "low": priority_counts.get(Task.Priority.LOW, 0),
                "medium": priority_counts.get(Task.Priority.MEDIUM, 0),
                "high": priority_counts.get(Task.Priority.HIGH, 0),
                "urgent": priority_counts.get(Task.Priority.URGENT, 0),
            },
            "overdue": overdue_count,
            "unassigned": qs.filter(assigned_to__isnull=True).exclude(
                status__in=[Task.Status.DONE, Task.Status.CANCELLED]
            ).count(),
        }

    # ─── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _get_task(task_id, organization: Organization) -> Task:
        try:
            return Task.objects.get(id=task_id, organization=organization)
        except Task.DoesNotExist:
            raise ServiceException(
                message="Task not found.",
                code="NOT_FOUND",
                status_code=404,
            )

    @staticmethod
    def _get_org_member_user(organization: Organization, user_id) -> User:
        """
        Return a User who is an active member of the organization.

        Raises:
            ServiceException(400) if user is not an org member.
        """
        is_member = OrganizationMembership.objects.filter(
            organization=organization,
            user_id=user_id,
            is_active=True,
        ).exists()
        if not is_member:
            raise ServiceException(
                message="The specified user is not a member of this organization.",
                code="NOT_ORG_MEMBER",
                status_code=400,
            )
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise ServiceException(
                message="User not found.",
                code="NOT_FOUND",
                status_code=404,
            )
