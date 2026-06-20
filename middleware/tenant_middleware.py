"""
Tenant Middleware.

Resolves the current Organization (tenant) from the incoming request.
Resolution strategy (in priority order):
  1. X-Organization-Slug header
  2. ?org= query parameter
  3. JWT token claim (organization_slug)

The resolved organization is attached to `request.organization` for use
throughout the request lifecycle (views, services, serializers).
"""
import logging

from django.utils.functional import SimpleLazyObject

logger = logging.getLogger(__name__)


def _get_organization_from_request(request):
    """
    Core tenant resolution logic.
    Returns an Organization instance or None.
    """
    from apps.organizations.models import Organization

    # ── 1. Header ──────────────────────────────────────────────────────────────
    slug = request.META.get("HTTP_X_ORGANIZATION_SLUG")

    # ── 2. Query param ─────────────────────────────────────────────────────────
    if not slug:
        slug = request.GET.get("org")

    # ── 3. JWT token claim ─────────────────────────────────────────────────────
    if not slug:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                token_str = auth_header.split(" ")[1]
                token = AccessToken(token_str)
                slug = token.get("organization_slug")
            except Exception:
                pass  # Invalid token; will be caught by DRF authentication

    if not slug:
        return None

    try:
        org = Organization.objects.get(slug=slug, is_active=True)
        return org
    except Organization.DoesNotExist:
        logger.warning("TenantMiddleware: unknown or inactive org slug '%s'", slug)
        return None


class TenantMiddleware:
    """
    Attaches `request.organization` (lazy) for every incoming request.
    Uses SimpleLazyObject so the DB hit only happens when actually accessed.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = SimpleLazyObject(
            lambda: _get_organization_from_request(request)
        )
        response = self.get_response(request)
        return response
