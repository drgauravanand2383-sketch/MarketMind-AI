"""Clock abstraction.

Every time-dependent decision in this framework (token `iat`/`exp`
computation, expiry/clock-skew checks) goes through an injected
`BaseClock` rather than calling `datetime.now()` directly — the same
`now_fn`-injection discipline every domain engine since Sprint 44 already
follows, formalized as its own named abstraction here since this sprint
explicitly asks for one (clock-skew testing needs a controllable clock,
not real wall-clock waits).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

__all__ = ["BaseClock", "SystemClock"]


class BaseClock(ABC):
    """Abstract base class every clock implementation must inherit."""

    @abstractmethod
    def now(self) -> datetime:
        """The current, timezone-aware (UTC) time."""
        raise NotImplementedError


class SystemClock(BaseClock):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
