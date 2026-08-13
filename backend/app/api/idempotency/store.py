"""`IdempotencyStore` — the provider-independent interface every concrete
duplicate-request-detection implementation must satisfy. No concrete
implementation ships this sprint; see `app.api.idempotency.models`'s own
module docstring for why that is intentional, not a gap.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.api.idempotency.models import IdempotencyRecord

__all__ = ["IdempotencyStore"]


class IdempotencyStore(ABC):
    """Detects duplicate `POST` submissions keyed by an `Idempotency-Key`
    header value. Implementations own their own storage (in-memory,
    Redis, a database, ...) and their own expiry policy — this interface
    makes no assumption about either.
    """

    @abstractmethod
    async def get(self, key: str) -> IdempotencyRecord | None:
        """Return the previously-stored record for `key`, or `None` if
        this key has never been seen (or has expired)."""
        raise NotImplementedError

    @abstractmethod
    async def put(self, record: IdempotencyRecord) -> None:
        """Store `record` under its own key. Implementations decide
        their own behavior when a key is already stored (reject,
        overwrite, or raise) — this interface does not prescribe one."""
        raise NotImplementedError
