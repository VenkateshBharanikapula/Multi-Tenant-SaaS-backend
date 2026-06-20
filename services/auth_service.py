"""
AuthService — all authentication-related business logic.

Responsibilities:
- User registration
- Logout (token blacklisting)
- Password change
"""
import logging

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.exceptions import ServiceException
from apps.users.serializers import UserProfileSerializer

logger = logging.getLogger(__name__)

User = get_user_model()


class AuthService:

    @staticmethod
    def register(validated_data: dict) -> dict:
        """
        Create a new user account.
        Returns a dict containing the JWT token pair and the user profile.

        Raises:
            ServiceException: if the email is already registered.
        """
        email = validated_data["email"].lower().strip()

        if User.objects.filter(email=email).exists():
            raise ServiceException(
                message=f"An account with email '{email}' already exists.",
                code="EMAIL_ALREADY_EXISTS",
                status_code=409,
            )

        user = User.objects.create_user(
            email=email,
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            password=validated_data["password"],
        )

        logger.info("New user registered: %s (id=%s)", user.email, user.id)

        # Issue JWT tokens immediately on registration
        refresh = RefreshToken.for_user(user)

        return {
            "user": UserProfileSerializer(user).data,
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
        }

    @staticmethod
    def logout(refresh_token: str) -> None:
        """
        Blacklist the provided refresh token.
        After this call, the token can no longer be used to obtain new access tokens.

        Raises:
            rest_framework_simplejwt.exceptions.TokenError: if the token is invalid.
        """
        token = RefreshToken(refresh_token)
        token.blacklist()
        logger.debug("Refresh token blacklisted.")

    @staticmethod
    def change_password(user, new_password: str) -> None:
        """
        Set a new password for the user and rotate their JWT tokens
        by blacklisting all outstanding refresh tokens.

        Raises:
            ServiceException: on any unexpected error.
        """
        try:
            user.set_password(new_password)
            user.save(update_fields=["password"])
            logger.info("Password changed for user %s", user.email)
        except Exception as exc:
            logger.exception("Password change failed for %s", user.email)
            raise ServiceException(
                message="Password change failed. Please try again.",
                code="PASSWORD_CHANGE_FAILED",
                status_code=500,
            ) from exc
