"""Centralized exception handling for the `/api/v1` REST API — converts
domain exceptions and framework-level errors into a consistent HTTP
response format. See `handlers.py` for the full handler catalog."""

from app.api.v1.exception_handlers.handlers import register_exception_handlers

__all__ = ["register_exception_handlers"]
