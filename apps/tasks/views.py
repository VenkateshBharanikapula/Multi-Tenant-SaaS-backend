"""
Task views — thin layer delegating all business logic to TaskService.
"""
import logging

from django.db.models import Count
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.exceptions import ServiceException
from apps.core.mixins import TenantQuerysetMixin
from apps.core.permissions import IsOrganizationAdmin, IsOrganizationMember
from services.task_service import TaskService

from .filters import TaskFilter
from .models import Task, TaskTag
from .serializers import (
    TaskAssignSerializer,
    TaskCommentCreateSerializer,
    TaskCommentSerializer,
    TaskCreateSerializer,
    TaskDetailSerializer,
    TaskListSerializer,
    TaskStatusUpdateSerializer,
    TaskTagCreateSerializer,
    TaskTagSerializer,
    TaskUpdateSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema(tags=["Tasks"])
@extend_schema_view(
    list=extend_schema(summary="List tasks in the current organization"),
    create=extend_schema(summary="Create a new task"),
    retrieve=extend_schema(summary="Get task details"),
    update=extend_schema(summary="Update a task"),
    partial_update=extend_schema(summary="Partially update a task"),
    destroy=extend_schema(summary="Delete a task"),
)
class TaskViewSet(TenantQuerysetMixin, GenericViewSet):
    """
    Full CRUD for tasks, scoped to the current organization.
    All list endpoints include server-side filtering + search + ordering.
    """

    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_class = TaskFilter
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "updated_at", "due_date", "priority", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        return (
            qs.select_related("assigned_to", "created_by", "parent")
            .prefetch_related("tags")
            .annotate(comment_count=Count("comments"))
        )

    @property
    def queryset(self):
        return Task.objects.all()

    def get_serializer_class(self):
        if self.action == "list":
            return TaskListSerializer
        if self.action == "create":
            return TaskCreateSerializer
        if self.action in ("update", "partial_update"):
            return TaskUpdateSerializer
        if self.action == "update_status":
            return TaskStatusUpdateSerializer
        if self.action == "assign":
            return TaskAssignSerializer
        if self.action in ("add_comment", "list_comments"):
            return TaskCommentSerializer
        return TaskDetailSerializer

    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TaskListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = TaskListSerializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            task = TaskService.create_task(
                organization=request.organization,
                created_by=request.user,
                validated_data=serializer.validated_data,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(
            TaskDetailSerializer(task).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        try:
            task = TaskService.get_task(
                task_id=pk,
                organization=request.organization,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(TaskDetailSerializer(task).data)

    def update(self, request, pk=None):
        return self._update(request, pk, partial=False)

    def partial_update(self, request, pk=None):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, partial):
        serializer = TaskUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            task = TaskService.update_task(
                task_id=pk,
                organization=request.organization,
                updated_by=request.user,
                validated_data=serializer.validated_data,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(TaskDetailSerializer(task).data)

    def destroy(self, request, pk=None):
        try:
            TaskService.delete_task(
                task_id=pk,
                organization=request.organization,
                deleted_by=request.user,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=TaskStatusUpdateSerializer,
        responses={200: TaskDetailSerializer},
        summary="Update task status",
    )
    @action(detail=True, methods=["patch"], url_path="status")
    def update_status(self, request, pk=None):
        serializer = TaskStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            task = TaskService.update_task_status(
                task_id=pk,
                organization=request.organization,
                new_status=serializer.validated_data["status"],
                updated_by=request.user,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(TaskDetailSerializer(task).data)

    @extend_schema(
        request=TaskAssignSerializer,
        responses={200: TaskDetailSerializer},
        summary="Assign or unassign a task",
    )
    @action(detail=True, methods=["patch"], url_path="assign")
    def assign(self, request, pk=None):
        serializer = TaskAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            task = TaskService.assign_task(
                task_id=pk,
                organization=request.organization,
                assignee_id=serializer.validated_data.get("assigned_to_id"),
                assigned_by=request.user,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(TaskDetailSerializer(task).data)

    @extend_schema(
        request=TaskCommentCreateSerializer,
        responses={201: TaskCommentSerializer},
        summary="Add a comment to a task",
    )
    @action(detail=True, methods=["post"], url_path="comments")
    def add_comment(self, request, pk=None):
        serializer = TaskCommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            comment = TaskService.add_comment(
                task_id=pk,
                organization=request.organization,
                author=request.user,
                body=serializer.validated_data["body"],
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(
            TaskCommentSerializer(comment).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        responses={200: TaskCommentSerializer(many=True)},
        summary="List comments for a task",
    )
    @action(detail=True, methods=["get"], url_path="comments/list")
    def list_comments(self, request, pk=None):
        try:
            comments = TaskService.get_task_comments(
                task_id=pk,
                organization=request.organization,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        serializer = TaskCommentSerializer(comments, many=True)
        return Response(serializer.data)

    @extend_schema(summary="Get a summary of task statistics for the organization")
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        try:
            stats = TaskService.get_task_stats(organization=request.organization)
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(stats)


@extend_schema(tags=["Tasks"])
class TaskTagViewSet(TenantQuerysetMixin, GenericViewSet):
    """
    Manage reusable task tags within an organization.
    """

    permission_classes = [IsAuthenticated, IsOrganizationMember]

    @property
    def queryset(self):
        return TaskTag.objects.all()

    def get_serializer_class(self):
        if self.action == "create":
            return TaskTagCreateSerializer
        return TaskTagSerializer

    def list(self, request):
        tags = self.get_queryset()
        return Response(TaskTagSerializer(tags, many=True).data)

    def create(self, request):
        serializer = TaskTagCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tag = TaskService.create_tag(
                organization=request.organization,
                validated_data=serializer.validated_data,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(TaskTagSerializer(tag).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        try:
            TaskService.delete_tag(
                tag_id=pk,
                organization=request.organization,
                requesting_user=request.user,
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
