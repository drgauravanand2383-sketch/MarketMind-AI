"""Domain models for the structured logging abstraction.

`LogCategory` covers exactly the five log surfaces the sprint names:
application, repository, service, startup, and validation logs. `LogRecord`
is the structured unit every `BaseStructuredLogger` implementation emits —
a plain, fully-typed Pydantic model, never a free-form string, so every
log emission is machine-parseable and independent of whatever backend
(stdlib logging, in-memory capture for tests, or a future vendor
integration) ultimately consumes it.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["LogCategory", "LogLevel", "LogRecord"]


class LogCategory(str, Enum):
    APPLICATION = "APPLICATION"
    REPOSITORY = "REPOSITORY"
    SERVICE = "SERVICE"
    STARTUP = "STARTUP"
    VALIDATION = "VALIDATION"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogRecord(BaseModel):
    """One structured log emission."""

    model_config = ConfigDict(extra="forbid")

    category: LogCategory
    level: LogLevel
    event: str
    context: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    timestamp: datetime
