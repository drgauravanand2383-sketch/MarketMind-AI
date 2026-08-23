"""Structured logging abstraction.

`BaseStructuredLogger` is the interface every part of this codebase that
wants structured (not free-form-string) logs depends on — never a
concrete vendor SDK. Two concrete implementations are provided:
`StdlibStructuredLogger` (wraps Python's own standard-library `logging`
module — not a third-party vendor, and the same logging infrastructure
`app.bootstrap.configure_logging` already sets up) for real use, and
`InMemoryStructuredLogger` (captures emitted `LogRecord`s in a list) for
tests and any caller that wants to inspect what was logged without
parsing stdlib log output.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime

from app.operations.logging.models import LogCategory, LogLevel, LogRecord

__all__ = ["BaseStructuredLogger", "StdlibStructuredLogger", "InMemoryStructuredLogger"]

_LEVEL_TO_STDLIB: dict[LogLevel, int] = {
    LogLevel.DEBUG: logging.DEBUG,
    LogLevel.INFO: logging.INFO,
    LogLevel.WARNING: logging.WARNING,
    LogLevel.ERROR: logging.ERROR,
    LogLevel.CRITICAL: logging.CRITICAL,
}


def _default_now() -> datetime:
    return datetime.now(UTC)


class BaseStructuredLogger(ABC):
    """Abstract base class every structured logger implementation must inherit."""

    @abstractmethod
    def log(
        self, category: LogCategory, level: LogLevel, event: str, **context: str | int | float | bool | None
    ) -> None:
        """Emit one structured log record."""
        raise NotImplementedError

    def debug(self, category: LogCategory, event: str, **context: str | int | float | bool | None) -> None:
        self.log(category, LogLevel.DEBUG, event, **context)

    def info(self, category: LogCategory, event: str, **context: str | int | float | bool | None) -> None:
        self.log(category, LogLevel.INFO, event, **context)

    def warning(self, category: LogCategory, event: str, **context: str | int | float | bool | None) -> None:
        self.log(category, LogLevel.WARNING, event, **context)

    def error(self, category: LogCategory, event: str, **context: str | int | float | bool | None) -> None:
        self.log(category, LogLevel.ERROR, event, **context)

    def critical(self, category: LogCategory, event: str, **context: str | int | float | bool | None) -> None:
        self.log(category, LogLevel.CRITICAL, event, **context)


class StdlibStructuredLogger(BaseStructuredLogger):
    def __init__(self, logger: logging.Logger, *, now_fn: Callable[[], datetime] = _default_now) -> None:
        self._logger = logger
        self._now_fn = now_fn

    def log(
        self, category: LogCategory, level: LogLevel, event: str, **context: str | int | float | bool | None
    ) -> None:
        record = LogRecord(category=category, level=level, event=event, context=context, timestamp=self._now_fn())
        self._logger.log(_LEVEL_TO_STDLIB[level], record.model_dump_json())


class InMemoryStructuredLogger(BaseStructuredLogger):
    def __init__(self, *, now_fn: Callable[[], datetime] = _default_now) -> None:
        self._now_fn = now_fn
        self._records: list[LogRecord] = []

    def log(
        self, category: LogCategory, level: LogLevel, event: str, **context: str | int | float | bool | None
    ) -> None:
        self._records.append(
            LogRecord(category=category, level=level, event=event, context=context, timestamp=self._now_fn())
        )

    @property
    def records(self) -> tuple[LogRecord, ...]:
        return tuple(self._records)

    def records_for(self, category: LogCategory) -> tuple[LogRecord, ...]:
        return tuple(record for record in self._records if record.category == category)
