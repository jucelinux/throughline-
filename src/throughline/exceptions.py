"""Service-layer exceptions, mapped to MCP errors at the boundary."""
from __future__ import annotations


class ServiceError(Exception):
    """Base for all service-layer errors."""


class NotFoundError(ServiceError):
    """Entity does not exist."""


class ValidationError(ServiceError):
    """Input failed validation."""


class TransitionError(ServiceError):
    """Status transition is not allowed."""


class ConflictError(ServiceError):
    """State conflicts with the requested operation."""
