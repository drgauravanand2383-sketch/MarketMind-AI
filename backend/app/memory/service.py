"""MemoryService — the production, in-process implementation of `MemoryInterface`.

Replaces `app.bootstrap.InProcessMemory` (a placeholder — see that class's
own docstring). MemoryService performs no reasoning, no summarization, and
calls neither KnowledgeHub nor WorkflowEngine: it is a typed, scope-aware
key/value store and nothing else.

Agents reach this service only through the narrow `MemoryInterface`
(`read`/`write`) via `BaseAgent.memory` — the richer scope-aware surface
below (`store`/`retrieve`/`delete`/`clear_scope`/`health_check`) is for
callers that need typed, scoped memory access directly (e.g. orchestration
code, tests), consistent with this project's existing pattern of a
concrete class satisfying a narrow interface while offering a richer API
of its own (see `WorkflowEngine`/`WorkflowProtocol`, `Scheduler`).

Storage is abstracted behind `BaseMemoryStore`, mirroring this codebase's
existing `BaseKnowledgeRepository`/`BaseEmbeddingProvider` pattern: this
sprint implements exactly one backend, `InProcessMemoryStore` — a single
in-process dict, with no persistence. Redis, PostgreSQL, ChromaDB, and
filesystem storage are all deliberately unimplemented; a future backend is
a new `BaseMemoryStore` subclass, not a change to MemoryService itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.memory.models import (
    MemoryEntry,
    MemoryHealthStatus,
    MemoryQuery,
    MemoryResult,
    MemoryScope,
)

__all__ = ["BaseMemoryStore", "InProcessMemoryStore", "MemoryService"]

_Address = tuple[MemoryScope, str | None, str]


class BaseMemoryStore(ABC):
    """Abstract storage backend `MemoryService` delegates all persistence to.

    Only this class needs a new subclass to add a Redis/PostgreSQL-backed
    store in a future sprint; `MemoryService`'s own overwrite/query
    semantics would not change.
    """

    @abstractmethod
    async def get(self, address: _Address) -> MemoryEntry | None:
        """Retrieve the entry stored at `address`, or None if absent."""
        raise NotImplementedError

    @abstractmethod
    async def set(self, address: _Address, entry: MemoryEntry) -> None:
        """Store `entry` at `address`, overwriting any existing entry there."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, address: _Address) -> bool:
        """Remove the entry at `address`. Returns True if it existed."""
        raise NotImplementedError

    @abstractmethod
    async def scan(self, scope: MemoryScope, scope_id: str | None) -> list[MemoryEntry]:
        """List every entry currently stored under (scope, scope_id)."""
        raise NotImplementedError

    @abstractmethod
    async def clear(self, scope: MemoryScope, scope_id: str | None) -> int:
        """Remove every entry under (scope, scope_id). Returns the count removed."""
        raise NotImplementedError

    @abstractmethod
    async def count_by_scope(self) -> dict[MemoryScope, int]:
        """Count currently stored entries, grouped by scope. Must not mutate storage."""
        raise NotImplementedError


class InProcessMemoryStore(BaseMemoryStore):
    """The only storage backend implemented this sprint: a single in-process dict.

    No persistence: every entry is lost when the process exits. No Redis,
    PostgreSQL, ChromaDB, or filesystem I/O occurs anywhere in this class.
    """

    def __init__(self) -> None:
        self._entries: dict[_Address, MemoryEntry] = {}

    async def get(self, address: _Address) -> MemoryEntry | None:
        return self._entries.get(address)

    async def set(self, address: _Address, entry: MemoryEntry) -> None:
        self._entries[address] = entry

    async def delete(self, address: _Address) -> bool:
        existed = address in self._entries
        self._entries.pop(address, None)
        return existed

    async def scan(self, scope: MemoryScope, scope_id: str | None) -> list[MemoryEntry]:
        return [
            entry
            for entry in self._entries.values()
            if entry.scope == scope and entry.scope_id == scope_id
        ]

    async def clear(self, scope: MemoryScope, scope_id: str | None) -> int:
        addresses = [
            address
            for address, entry in self._entries.items()
            if entry.scope == scope and entry.scope_id == scope_id
        ]
        for address in addresses:
            del self._entries[address]
        return len(addresses)

    async def count_by_scope(self) -> dict[MemoryScope, int]:
        counts: dict[MemoryScope, int] = {scope: 0 for scope in MemoryScope}
        for entry in self._entries.values():
            counts[entry.scope] += 1
        return counts


class MemoryService:
    """Typed, scope-aware memory storage. Implements `MemoryInterface`.

    No module-level singleton: whoever assembles the application (or a
    test) constructs exactly one MemoryService and injects it wherever a
    `MemoryInterface` is required (e.g. `AgentRuntime(memory=...)`).
    """

    def __init__(self, store: BaseMemoryStore | None = None) -> None:
        """Initialize with a storage backend.

        Args:
            store: The backend to delegate persistence to. Defaults to a
                fresh `InProcessMemoryStore` — the only backend this
                sprint implements.
        """
        self._store = store if store is not None else InProcessMemoryStore()

    # ------------------------------------------------------------------
    # MemoryInterface conformance
    # ------------------------------------------------------------------

    async def read(self, key: str) -> Any:
        """Implements `MemoryInterface.read`.

        Operates on `MemoryScope.GLOBAL`: `MemoryInterface`'s flat,
        scope-less signature has no room for a scope/scope_id, so
        `read`/`write` are defined against the one scope that needs
        neither. Scoped memory access goes through `retrieve()`/`store()`
        instead.
        """
        entry = await self._store.get((MemoryScope.GLOBAL, None, key))
        return entry.value if entry is not None else None

    async def write(self, key: str, value: Any) -> None:
        """Implements `MemoryInterface.write`. See `read()` for the scope note."""
        await self.store(MemoryEntry(key=key, value=value, scope=MemoryScope.GLOBAL))

    # ------------------------------------------------------------------
    # Typed, scope-aware operations
    # ------------------------------------------------------------------

    async def store(self, entry: MemoryEntry) -> MemoryEntry:
        """Store `entry`, keyed by `(entry.scope, entry.scope_id, entry.key)`.

        Overwrite behavior (explicitly defined): if an entry already
        exists at that address, the new entry replaces it entirely, except
        `created_at` is carried over from the existing entry — so a
        value's original creation time survives repeated overwrites —
        while `updated_at` is taken from the new entry as given (defaults
        to now if not set explicitly).

        Returns:
            The entry as actually stored (i.e. with `created_at` possibly
            rewritten per the rule above).
        """
        address: _Address = (entry.scope, entry.scope_id, entry.key)
        existing = await self._store.get(address)
        if existing is not None:
            entry = entry.model_copy(update={"created_at": existing.created_at})
        await self._store.set(address, entry)
        return entry

    async def retrieve(self, query: MemoryQuery) -> MemoryResult:
        """Look up entries matching `query`. Never raises on a no-match — returns an empty MemoryResult."""
        if query.key is not None:
            entry = await self._store.get((query.scope, query.scope_id, query.key))
            if entry is not None and (query.term is None or entry.term == query.term):
                return MemoryResult(entries=[entry])
            return MemoryResult(entries=[])

        matches = await self._store.scan(query.scope, query.scope_id)
        if query.term is not None:
            matches = [entry for entry in matches if entry.term == query.term]
        return MemoryResult(entries=matches)

    async def delete(self, scope: MemoryScope, key: str, scope_id: str | None = None) -> bool:
        """Delete one entry. Returns True if it existed, False if it was already absent."""
        return await self._store.delete((scope, scope_id, key))

    async def clear_scope(self, scope: MemoryScope, scope_id: str | None = None) -> int:
        """Remove every entry under (scope, scope_id). Returns the number removed."""
        return await self._store.clear(scope, scope_id)

    async def health_check(self) -> MemoryHealthStatus:
        """Report storage state. Never mutates storage."""
        scope_counts = await self._store.count_by_scope()
        return MemoryHealthStatus(
            healthy=True,
            entry_count=sum(scope_counts.values()),
            scope_counts=scope_counts,
        )
