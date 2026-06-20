from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import NotificationPreferenceViewSet, NotificationViewSet

app_name = "notifications"

router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notifications")
router.register(r"notifications", NotificationPreferenceViewSet, basename="notification-prefs")

urlpatterns = [
    path("", include(router.urls)),
]
