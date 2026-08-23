"""Schemas for the Embedding Service.

EmbeddingRequest represents a single unit of text prepared for a future
embedding API call. EmbeddingBatch groups validated requests into
size-bounded chunks — no embedding API is called and no vectors are
produced anywhere in this package.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "RejectionReason",
    "RejectedDocument",
    "EmbeddingRequest",
    "EmbeddingChunk",
    "EmbeddingBatchMetadata",
    "EmbeddingBatch",
]


class RejectionReason(StrEnum):
    """Why a VectorDocument was excluded from an EmbeddingBatch."""

    MISSING_ID = "missing_id"
    EMPTY_TEXT = "empty_text"
    DUPLICATE_ID = "duplicate_id"


class RejectedDocument(BaseModel):
    """A record of one VectorDocument excluded from embedding, and why."""

    model_config = ConfigDict(extra="forbid")

    document_index: int
    document_id: str | None
    reason: RejectionReason
    detail: str | None = None


class EmbeddingRequest(BaseModel):
    """A single unit of text prepared for a future embedding API call."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingChunk(BaseModel):
    """One sub-batch of EmbeddingRequests, sized to `max_batch_size`."""

    model_config = ConfigDict(extra="forbid")

    chunk_index: int
    requests: list[EmbeddingRequest] = Field(default_factory=list)


class EmbeddingBatchMetadata(BaseModel):
    """Batch-level outcome of one embedding preparation run."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str
    created_at: datetime
    total_documents_received: int
    accepted_count: int
    rejected_documents: list[RejectedDocument] = Field(default_factory=list)
    max_batch_size: int
    chunk_count: int


class EmbeddingBatch(BaseModel):
    """The output of EmbeddingService.prepare_batch()."""

    model_config = ConfigDict(extra="forbid")

    chunks: list[EmbeddingChunk] = Field(default_factory=list)
    batch_metadata: EmbeddingBatchMetadata
