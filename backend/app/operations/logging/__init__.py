"""Structured logging abstraction: application, repository, service,
startup, and validation logs — via `BaseStructuredLogger`, never a
concrete vendor SDK."""

from app.operations.logging.logger import (
    BaseStructuredLogger,
    InMemoryStructuredLogger,
    StdlibStructuredLogger,
)
from app.operations.logging.models import LogCategory, LogLevel, LogRecord

__all__ = [
    "BaseStructuredLogger",
    "StdlibStructuredLogger",
    "InMemoryStructuredLogger",
    "LogCategory",
    "LogLevel",
    "LogRecord",
]
