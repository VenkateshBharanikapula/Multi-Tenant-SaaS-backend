"""
ASGI config for SaaS Backend project.
Supports both HTTP and WebSocket (future-ready).
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
