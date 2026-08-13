"""Generic in-process, HTTP-layer-only store for computed results that
have no backing persistence in their owning domain package.

Three Sprint 58 domains — Company Research, Screening, Signal Detection —
have services that are either read-only (`CompanyResearchAgent` never
writes anywhere) or pure/stateless (`ScreeningEngine.evaluate_companies`,
`SignalDetectionService.evaluate_companies` are synchronous, no I/O).
None of them persist anything with an id, unlike Risk/Recommendation/
Backtesting/Explainability, which already do. This store exists ONLY so
a `GET .../{id}` endpoint has something to return after a POST computed
something — it never scores, evaluates, or otherwise duplicates any
business rule; it is pure bookkeeping.

**Known limitation:** in-process memory only. Cleared on restart, not
shared across multiple app instances/workers. A future sprint should
replace this with real repository-backed persistence in the owning
domain package if multi-instance deployment requires it.
"""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

__all__ = ["InMemoryResultStore", "ResultNotFoundError"]

T = TypeVar("T")


class ResultNotFoundError(Exception):
    """Raised when no cached result exists for the given id.

    Not a domain-package exception — an API-layer-only lookup miss for
    `InMemoryResultStore`. Registered against the same centralized
    `handle_domain_error` as the real domain exceptions purely for a
    consistent error response shape (`*NotFoundError` -> 404).
    """

    def __init__(self, kind: str, result_id: str) -> None:
        self.kind = kind
        self.result_id = result_id
        super().__init__(f"No {kind} found with id {result_id!r}.")


class InMemoryResultStore(Generic[T]):
    """Stores values keyed by a freshly generated id."""

    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._items: dict[str, T] = {}

    def put(self, value: T) -> str:
        """Store `value` under a freshly generated id and return that id."""
        item_id = str(uuid.uuid4())
        self._items[item_id] = value
        return item_id

    def get(self, item_id: str) -> T:
        """Raises `ResultNotFoundError` if no value exists for `item_id`."""
        value = self._items.get(item_id)
        if value is None:
            raise ResultNotFoundError(self._kind, item_id)
        return value
