from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MembershipViewSet, OrganizationViewSet

app_name = "organizations"

router = DefaultRouter()
router.register(r"organizations", OrganizationViewSet, basename="organizations")
router.register(r"members", MembershipViewSet, basename="members")

urlpatterns = [
    path("", include(router.urls)),
]
