from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import TaskTagViewSet, TaskViewSet

app_name = "tasks"

router = DefaultRouter()
router.register(r"tasks", TaskViewSet, basename="tasks")
router.register(r"task-tags", TaskTagViewSet, basename="task-tags")

urlpatterns = [
    path("", include(router.urls)),
]
