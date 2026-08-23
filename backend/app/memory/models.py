"""Typed models for the Memory Service.

`MemoryEntry` / `MemoryScope` / `MemoryTerm` / `MemoryQuery` / `MemoryResult`
/ `MemoryHealthStatus` define the storage and retrieval shapes
`app.memory.service.MemoryService` operates on. No reasoning,
summarization, or domain-specific knowledge lives here — `MemoryEntry.value`
is intentionally untyped (`Any`), since the Memory Service is a generic
key/value store, independent of what any given agent or workflow chooses
to remember, and independent of KnowledgeHub.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "MemoryScope",
    "MemoryTerm",
    "MemoryEntry",
    "MemoryQuery",
    "MemoryResult",
    "MemoryHealthStatus",
]


class MemoryScope(StrEnum):
    """Which namespace a memory entry belongs to.

    Every scope except GLOBAL requires a `scope_id` identifying which
    workflow/conversation/user/agent the entry belongs to (e.g. a
    WORKFLOW-scoped entry needs the execution or workflow id it's
    attached to). GLOBAL is the single shared bucket and takes no id.
    """

    WORKFLOW = "workflow"
    CONVERSATION = "conversation"
    USER = "user"
    AGENT = "agent"
    GLOBAL = "global"


class MemoryTerm(StrEnum):
    """Whether an entry is short-term (working/session state) or long-term
    (meant to persist across sessions).

    This sprint's in-process store treats both terms identically for
    storage and retrieval — no eviction, TTL, or retention policy is
    implemented for either (see service.py's module docstring). `term` is
    a classification callers can filter on now, so a future backend that
    actually enforces different retention per term is a storage-layer
    change only, not a model or query-shape change.
    """

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


def _validate_scope_id(scope: MemoryScope, scope_id: str | None) -> None:
    """Shared scope/scope_id consistency rule for MemoryEntry and MemoryQuery."""
    if scope is MemoryScope.GLOBAL:
        if scope_id is not None:
            raise ValueError("scope_id must not be set when scope is GLOBAL")
    elif not scope_id:
        raise ValueError(f"scope_id is required when scope is {scope.value!r}")


class MemoryEntry(BaseModel):
    """One stored memory value, addressed by (scope, scope_id, key).

    Frozen: `MemoryService.store()` never mutates an existing MemoryEntry
    in place, it replaces it with a new one — see `MemoryService.store()`'s
    docstring for the exact overwrite rule (`created_at` is preserved from
    the prior entry; `updated_at` reflects the new write).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)
    value: Any
    scope: MemoryScope
    scope_id: str | None = None
    term: MemoryTerm = MemoryTerm.SHORT_TERM
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _validate_scope(self) -> MemoryEntry:
        _validate_scope_id(self.scope, self.scope_id)
        return self

    @model_validator(mode="after")
    def _validate_timestamps(self) -> MemoryEntry:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be before created_at")
        return self


class MemoryQuery(BaseModel):
    """A request to `MemoryService.retrieve()`.

    If `key` is set, `retrieve()` looks up exactly that entry (0 or 1
    results). If `key` is omitted, `retrieve()` returns every entry in
    `(scope, scope_id)`, optionally narrowed further by `term`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: MemoryScope
    scope_id: str | None = None
    key: str | None = Field(default=None, min_length=1)
    term: MemoryTerm | None = None

    @model_validator(mode="after")
    def _validate_scope(self) -> MemoryQuery:
        _validate_scope_id(self.scope, self.scope_id)
        return self


class MemoryResult(BaseModel):
    """The output of `MemoryService.retrieve()`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entries: list[MemoryEntry] = Field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.entries)


class MemoryHealthStatus(BaseModel):
    """`MemoryService.health_check()`'s result. Never reflects a storage mutation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    healthy: bool
    entry_count: int
    scope_counts: dict[MemoryScope, int]
