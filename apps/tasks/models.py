"""
Task management models — fully scoped to an Organization.
"""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.organizations.models import Organization


class Task(BaseModel):
    """
    Core task entity. Always belongs to an Organization.
    """

    class Status(models.TextChoices):
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        IN_REVIEW = "in_review", "In Review"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    # ── Tenant isolation ────────────────────────────────────────────────────────
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="tasks",
        db_index=True,
    )

    # ── Core fields ─────────────────────────────────────────────────────────────
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TODO, db_index=True
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.MEDIUM, db_index=True
    )

    # ── People ──────────────────────────────────────────────────────────────────
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_tasks",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
        db_index=True,
    )

    # ── Dates ────────────────────────────────────────────────────────────────────
    due_date = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # ── Relations ────────────────────────────────────────────────────────────────
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subtasks",
    )
    tags = models.ManyToManyField("TaskTag", blank=True, related_name="tasks")

    class Meta:
        db_table = "tasks"
        ordering = ["-created_at"]
        verbose_name = "Task"
        verbose_name_plural = "Tasks"
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "assigned_to"]),
            models.Index(fields=["organization", "priority"]),
        ]

    def __str__(self):
        return f"[{self.organization.slug}] {self.title}"

    @property
    def is_completed(self) -> bool:
        return self.status == self.Status.DONE

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone
        return (
            self.due_date is not None
            and self.due_date < timezone.now()
            and self.status not in (self.Status.DONE, self.Status.CANCELLED)
        )


class TaskComment(BaseModel):
    """Comments on a task — also tenant-scoped."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="task_comments",
    )
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="task_comments",
    )
    body = models.TextField()

    class Meta:
        db_table = "task_comments"
        ordering = ["created_at"]
        verbose_name = "Task Comment"
        verbose_name_plural = "Task Comments"

    def __str__(self):
        return f"Comment on {self.task.title} by {self.author}"


class TaskTag(BaseModel):
    """Reusable labels/tags scoped to an organization."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="task_tags",
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default="#3B82F6")  # hex color

    class Meta:
        db_table = "task_tags"
        unique_together = ("organization", "name")
        ordering = ["name"]
        verbose_name = "Task Tag"
        verbose_name_plural = "Task Tags"

    def __str__(self):
        return f"{self.organization.slug}/{self.name}"


class TaskActivity(BaseModel):
    """
    Audit log of all changes to a task.
    Append-only: never updated or deleted.
    """

    class ActivityType(models.TextChoices):
        CREATED = "created", "Created"
        STATUS_CHANGED = "status_changed", "Status Changed"
        ASSIGNED = "assigned", "Assigned"
        UNASSIGNED = "unassigned", "Unassigned"
        COMMENTED = "commented", "Commented"
        UPDATED = "updated", "Updated"
        DELETED = "deleted", "Deleted"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="task_activities",
    )
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="activities")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="task_activities",
    )
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
    metadata = models.JSONField(default=dict)  # e.g. {"from": "todo", "to": "done"}

    class Meta:
        db_table = "task_activities"
        ordering = ["-created_at"]
        verbose_name = "Task Activity"
        verbose_name_plural = "Task Activities"

    def __str__(self):
        return f"{self.activity_type} on {self.task.title}"
