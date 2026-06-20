"""
Core abstract base models shared across the entire application.
"""
import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """
    Abstract base class providing self-managed `created_at` and `updated_at` fields.
    All models in this project inherit from this.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """
    Abstract base class using UUID as primary key.
    Prevents sequential ID enumeration attacks.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """
    Convenience base combining UUID primary key + timestamps.
    Used as the foundation for all domain models.
    """

    class Meta:
        abstract = True
