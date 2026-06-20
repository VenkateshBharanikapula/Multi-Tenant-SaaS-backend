from django.contrib import admin

from .models import Task, TaskActivity, TaskComment, TaskTag


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 0
    readonly_fields = ("id", "author", "created_at")
    fields = ("author", "body", "created_at")


class TaskActivityInline(admin.TabularInline):
    model = TaskActivity
    extra = 0
    readonly_fields = ("id", "actor", "activity_type", "metadata", "created_at")
    fields = ("actor", "activity_type", "metadata", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "title", "organization", "status", "priority",
        "assigned_to", "created_by", "due_date", "created_at",
    )
    list_filter = ("status", "priority", "organization")
    search_fields = ("title", "description", "organization__name")
    readonly_fields = ("id", "created_at", "updated_at", "completed_at")
    raw_id_fields = ("organization", "assigned_to", "created_by", "parent")
    filter_horizontal = ("tags",)
    inlines = [TaskCommentInline, TaskActivityInline]

    fieldsets = (
        (None, {"fields": ("id", "organization", "title", "description")}),
        ("Status", {"fields": ("status", "priority", "due_date", "completed_at")}),
        ("People", {"fields": ("created_by", "assigned_to")}),
        ("Relations", {"fields": ("parent", "tags")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(TaskTag)
class TaskTagAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "organization")
    search_fields = ("name", "organization__name")
    list_filter = ("organization",)
    readonly_fields = ("id",)


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ("task", "author", "created_at")
    search_fields = ("task__title", "author__email", "body")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("task", "author", "organization")


@admin.register(TaskActivity)
class TaskActivityAdmin(admin.ModelAdmin):
    list_display = ("task", "actor", "activity_type", "created_at")
    list_filter = ("activity_type",)
    search_fields = ("task__title", "actor__email")
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("task", "actor", "organization")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
