"""
User views — thin layer that delegates to the auth service.
"""
import logging

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from apps.core.exceptions import ServiceException
from services.auth_service import AuthService

from .serializers import (
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
    UserUpdateSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema(tags=["Auth"])
class LoginView(TokenObtainPairView):
    """
    Obtain JWT access + refresh tokens.
    Returns user profile alongside tokens.
    """

    serializer_class = CustomTokenObtainPairSerializer


@extend_schema(tags=["Auth"])
class TokenRefreshExtendedView(TokenRefreshView):
    """Refresh the access token using a valid refresh token."""


@extend_schema(tags=["Auth"])
class RegisterView(GenericViewSet):
    """User registration endpoint."""

    permission_classes = [AllowAny]
    serializer_class = UserRegistrationSerializer

    @extend_schema(
        request=UserRegistrationSerializer,
        responses={201: UserProfileSerializer},
        summary="Register a new user",
    )
    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = AuthService.register(
                validated_data=serializer.validated_data
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(result, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None,
        responses={204: None},
        summary="Logout (blacklist refresh token)",
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="logout",
        permission_classes=[IsAuthenticated],
    )
    def logout(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": {"code": "BAD_REQUEST", "message": "Refresh token is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            AuthService.logout(refresh_token=refresh_token)
        except TokenError as exc:
            return Response(
                {"error": {"code": "INVALID_TOKEN", "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Users"])
@extend_schema_view(
    retrieve=extend_schema(summary="Get user profile"),
    update=extend_schema(summary="Update user profile"),
    partial_update=extend_schema(summary="Partially update user profile"),
)
class UserViewSet(GenericViewSet):
    """Authenticated user's own profile management."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        if self.action == "change_password":
            return ChangePasswordSerializer
        return UserProfileSerializer

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        """Return the authenticated user's profile."""
        serializer = UserProfileSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["patch"], url_path="me/update")
    def update_me(self, request):
        """Update the authenticated user's profile."""
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserProfileSerializer(user, context={"request": request}).data
        )

    @action(detail=False, methods=["post"], url_path="me/change-password")
    def change_password(self, request):
        """Change the authenticated user's password."""
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            AuthService.change_password(
                user=request.user,
                new_password=serializer.validated_data["new_password"],
            )
        except ServiceException as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response({"detail": "Password updated successfully."})
