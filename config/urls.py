"""
Root URL configuration for SaaS Backend.
"""
from django.contrib import admin
from django.urls import include, path
from django.http import HttpResponse

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

API_V1 = "api/v1/"

# ─── Simple Home Page ─────────────────────────────────────────────────────────
def home(request):
    return HttpResponse("SaaS Backend is running 🚀")

urlpatterns = [
    # ─── Home ────────────────────────────────────────────────────────────────
    path("", home),

    # ─── Admin ───────────────────────────────────────────────────────────────
    path("admin/", admin.site.urls),

    # ─── API v1 ───────────────────────────────────────────────────────────────
    path(API_V1, include("apps.users.urls", namespace="users")),
    path(API_V1, include("apps.organizations.urls", namespace="organizations")),
    path(API_V1, include("apps.tasks.urls", namespace="tasks")),
    path(API_V1, include("apps.notifications.urls", namespace="notifications")),

    # ─── OpenAPI / Swagger ────────────────────────────────────────────────────
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]