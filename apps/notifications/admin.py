from django.contrib import admin

from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "recipient", "organization", "event_type", "title", "is_read", "created_at"
    )
    list_filter = ("event_type", "is_read", "organization")
    search_fields = ("recipient__email", "title", "body")
    readonly_fields = ("id", "created_at", "read_at")
    raw_id_fields = ("recipient", "actor", "organization")

    fieldsets = (
        (None, {"fields": ("id", "organization", "recipient", "actor")}),
        ("Content", {"fields": ("event_type", "title", "body", "data")}),
        ("State", {"fields": ("is_read", "read_at")}),
        ("Timestamps", {"fields": ("created_at",)}),
    )


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "in_app", "email")
    search_fields = ("user__email", "organization__name")
    list_filter = ("organization", "in_app", "email")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("user", "organization")
