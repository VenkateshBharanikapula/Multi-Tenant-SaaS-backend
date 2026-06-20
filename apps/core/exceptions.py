"""
Custom exception handler for consistent API error responses.
"""
import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns a consistent JSON error structure:
    {
        "error": {
            "code": "ERROR_CODE",
            "message": "Human-readable message",
            "details": {...}   # optional
        }
    }
    """
    # First, let DRF handle the exception
    response = exception_handler(exc, context)

    if response is not None:
        error_payload = {
            "error": {
                "code": _get_error_code(response.status_code),
                "message": _extract_message(response.data),
                "details": response.data,
            }
        }
        response.data = error_payload
        return response

    # Handle Django exceptions not caught by DRF
    if isinstance(exc, Http404):
        return Response(
            {"error": {"code": "NOT_FOUND", "message": "Resource not found."}},
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, PermissionDenied):
        return Response(
            {"error": {"code": "PERMISSION_DENIED", "message": "Permission denied."}},
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, ValidationError):
        return Response(
            {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Validation failed.",
                    "details": exc.message_dict if hasattr(exc, "message_dict") else str(exc),
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Unhandled exception — log it and return 500
    logger.exception("Unhandled exception: %s", exc)
    return Response(
        {"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."}},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _get_error_code(status_code: int) -> str:
    mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "UNPROCESSABLE_ENTITY",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_SERVER_ERROR",
    }
    return mapping.get(status_code, "ERROR")


def _extract_message(data) -> str:
    if isinstance(data, dict):
        # DRF wraps non-field errors under 'detail' or 'non_field_errors'
        if "detail" in data:
            return str(data["detail"])
        if "non_field_errors" in data:
            return str(data["non_field_errors"][0])
        # First field error
        for key, value in data.items():
            if isinstance(value, list) and value:
                return f"{key}: {value[0]}"
    if isinstance(data, list) and data:
        return str(data[0])
    return str(data)


class ServiceException(Exception):
    """
    Base exception raised by the service layer.
    Views should catch this and return appropriate HTTP responses.
    """

    def __init__(self, message: str, code: str = "SERVICE_ERROR", status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class TenantMismatchException(ServiceException):
    """Raised when a resource does not belong to the current tenant."""

    def __init__(self, message: str = "Resource does not belong to your organization."):
        super().__init__(message, code="TENANT_MISMATCH", status_code=403)


class OrganizationRequiredException(ServiceException):
    """Raised when a request requires an organization context but none is set."""

    def __init__(self, message: str = "Organization context is required for this operation."):
        super().__init__(message, code="ORGANIZATION_REQUIRED", status_code=400)
