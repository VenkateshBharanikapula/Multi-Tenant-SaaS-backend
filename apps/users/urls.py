"""
URL patterns for the users app.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LoginView, RegisterView, TokenRefreshExtendedView, UserViewSet

app_name = "users"

router = DefaultRouter()
router.register(r"auth", RegisterView, basename="auth")
router.register(r"users", UserViewSet, basename="users")

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/token/refresh/", TokenRefreshExtendedView.as_view(), name="token-refresh"),
    path("", include(router.urls)),
]
