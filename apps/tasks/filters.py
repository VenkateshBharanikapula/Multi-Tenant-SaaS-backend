"""
Django-filter FilterSet for Task queries.
"""
import django_filters

from .models import Task


class TaskFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=Task.Status.choices)
    priority = django_filters.MultipleChoiceFilter(choices=Task.Priority.choices)
    assigned_to = django_filters.UUIDFilter(field_name="assigned_to__id")
    created_by = django_filters.UUIDFilter(field_name="created_by__id")
    due_before = django_filters.DateTimeFilter(field_name="due_date", lookup_expr="lte")
    due_after = django_filters.DateTimeFilter(field_name="due_date", lookup_expr="gte")
    tag = django_filters.UUIDFilter(field_name="tags__id")
    is_overdue = django_filters.BooleanFilter(method="filter_overdue")
    unassigned = django_filters.BooleanFilter(method="filter_unassigned")

    class Meta:
        model = Task
        fields = ["status", "priority", "assigned_to", "created_by"]

    def filter_overdue(self, queryset, name, value):
        from django.utils import timezone
        now = timezone.now()
        if value:
            return queryset.filter(
                due_date__lt=now
            ).exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED])
        return queryset.exclude(
            due_date__lt=now
        ).exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED])

    def filter_unassigned(self, queryset, name, value):
        if value:
            return queryset.filter(assigned_to__isnull=True)
        return queryset.filter(assigned_to__isnull=False)
