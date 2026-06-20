"""
View mixins for multi-tenant querysets and common patterns.
"""
from apps.core.exceptions import OrganizationRequiredException


class TenantQuerysetMixin:
    """
    Automatically filters querysets to the current organization.
    Raises OrganizationRequiredException if no org is resolved.

    Usage:
        class TaskViewSet(TenantQuerysetMixin, ModelViewSet):
            queryset = Task.objects.all()
            ...
    """

    tenant_field = "organization"

    def get_queryset(self):
        queryset = super().get_queryset()
        org = getattr(self.request, "organization", None)
        if org is None:
            raise OrganizationRequiredException()
        return queryset.filter(**{self.tenant_field: org})

    def perform_create(self, serializer):
        org = getattr(self.request, "organization", None)
        if org is None:
            raise OrganizationRequiredException()
        serializer.save(**{self.tenant_field: org})
