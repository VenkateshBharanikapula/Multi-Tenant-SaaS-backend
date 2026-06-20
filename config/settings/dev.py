"""
Development settings.
"""
from .base import *  # noqa

DEBUG = True

ALLOWED_HOSTS = ["*"]

# ─── Email override for dev ───────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ─── Django Debug Toolbar (optional) ─────────────────────────────────────────
INSTALLED_APPS += ["django_extensions"]  # noqa: F405

# ─── Disable HTTPS requirements ───────────────────────────────────────────────
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# ─── Relaxed CORS for local frontend ─────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True

# ─── Logging override ─────────────────────────────────────────────────────────
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
