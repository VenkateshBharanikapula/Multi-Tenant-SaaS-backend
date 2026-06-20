"""
Task serializers.
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.serializers import UserMinimalSerializer

from .models import Task, TaskActivity, TaskComment, TaskTag

User = get_user_model()


class TaskTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTag
        fields = ("id", "name", "color")
        read_only_fields = ("id",)


class TaskTagCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTag
        fields = ("name", "color")

    def validate_color(self, value):
        if not value.startswith("#") or len(value) not in (4, 7):
            raise serializers.ValidationError("Color must be a valid hex code (e.g. #3B82F6).")
        return value


class TaskCommentSerializer(serializers.ModelSerializer):
    author = UserMinimalSerializer(read_only=True)

    class Meta:
        model = TaskComment
        fields = ("id", "author", "body", "created_at", "updated_at")
        read_only_fields = ("id", "author", "created_at", "updated_at")


class TaskCommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskComment
        fields = ("body",)

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError("Comment body cannot be empty.")
        return value.strip()


class TaskActivitySerializer(serializers.ModelSerializer):
    actor = UserMinimalSerializer(read_only=True)

    class Meta:
        model = TaskActivity
        fields = ("id", "actor", "activity_type", "metadata", "created_at")
        read_only_fields = fields


class TaskListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    assigned_to = UserMinimalSerializer(read_only=True)
    created_by = UserMinimalSerializer(read_only=True)
    tags = TaskTagSerializer(many=True, read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "title",
            "status",
            "priority",
            "assigned_to",
            "created_by",
            "due_date",
            "is_overdue",
            "tags",
            "comment_count",
            "created_at",
        )
        read_only_fields = fields


class TaskDetailSerializer(serializers.ModelSerializer):
    """Full task detail including comments and activity."""

    assigned_to = UserMinimalSerializer(read_only=True)
    created_by = UserMinimalSerializer(read_only=True)
    tags = TaskTagSerializer(many=True, read_only=True)
    comments = TaskCommentSerializer(many=True, read_only=True)
    activities = TaskActivitySerializer(many=True, read_only=True)
    subtasks = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    comment_count = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = (
            "id",
            "title",
            "description",
            "status",
            "priority",
            "assigned_to",
            "created_by",
            "due_date",
            "completed_at",
            "is_overdue",
            "parent",
            "subtasks",
            "tags",
            "comments",
            "activities",
            "comment_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id", "created_by", "completed_at", "created_at", "updated_at"
        )

    def get_subtasks(self, obj):
        return TaskListSerializer(obj.subtasks.all(), many=True).data

    def get_comment_count(self, obj):
        return obj.comments.count()


class TaskCreateSerializer(serializers.ModelSerializer):
    """Used when creating a new task."""

    assigned_to_id = serializers.UUIDField(required=False, allow_null=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, write_only=True
    )

    class Meta:
        model = Task
        fields = (
            "title",
            "description",
            "status",
            "priority",
            "assigned_to_id",
            "due_date",
            "parent_id",
            "tag_ids",
        )

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Task title cannot be empty.")
        return value.strip()


class TaskUpdateSerializer(serializers.ModelSerializer):
    """Used when updating an existing task."""

    assigned_to_id = serializers.UUIDField(required=False, allow_null=True)
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, write_only=True
    )

    class Meta:
        model = Task
        fields = (
            "title",
            "description",
            "status",
            "priority",
            "assigned_to_id",
            "due_date",
            "tag_ids",
        )


class TaskStatusUpdateSerializer(serializers.Serializer):
    """Used for targeted status updates."""

    status = serializers.ChoiceField(choices=Task.Status.choices)


class TaskAssignSerializer(serializers.Serializer):
    """Assign or unassign a task to a user."""

    assigned_to_id = serializers.UUIDField(allow_null=True)
