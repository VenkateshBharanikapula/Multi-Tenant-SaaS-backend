from django.contrib import admin

from .models import Organization, OrganizationMembership


class MembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0
    readonly_fields = ("id", "created_at", "joined_at")
    fields = ("user", "role", "is_active", "invited_by", "joined_at")
    autocomplete_fields = ("user",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner", "is_active", "member_count", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "owner__email")
    readonly_fields = ("id", "slug", "created_at", "updated_at")
    raw_id_fields = ("owner",)
    inlines = [MembershipInline]

    fieldsets = (
        (None, {"fields": ("id", "name", "slug", "description", "website", "logo")}),
        ("Status", {"fields": ("is_active", "owner")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "organization__name")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("user", "organization", "invited_by")
