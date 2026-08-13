"""Schemas for the Knowledge Repository abstraction.

These models define the persistence and retrieval contracts for knowledge
storage — no database or vector store implementation exists here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "SaveResult",
    "SearchQuery",
    "SearchResult",
    "KnowledgeRecord",
    "DeleteResult",
]


class SaveResult(BaseModel):
    """The outcome of persisting one batch of knowledge."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str
    saved_at: datetime
    vector_count: int
    relational_count: int
    success: bool
    errors: list[str] = Field(default_factory=list)


class SearchQuery(BaseModel):
    """A request to retrieve knowledge records.

    `semantic` was added for CompositeKnowledgeRepository (AGT knowledge
    layer, Sprint 26) to route between backends: False (the default)
    requests structured/relational search, True requests vector/semantic
    search. Existing single-backend repositories (Postgres, Chroma) do
    not need to inspect this field themselves — only a composite that
    owns more than one backend does.
    """

    model_config = ConfigDict(extra="forbid")

    query_text: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = 10
    semantic: bool = False


class SearchResult(BaseModel):
    """A single knowledge record matched by a search."""

    model_config = ConfigDict(extra="forbid")

    id: str
    score: float | None = None
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeRecord(BaseModel):
    """A single stored knowledge record, as returned by `get`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None = None
    text: str | None = None
    url: str | None = None
    published_at: str | None = None
    source_provider_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeleteResult(BaseModel):
    """The outcome of deleting a single knowledge record."""

    model_config = ConfigDict(extra="forbid")

    id: str
    deleted: bool
