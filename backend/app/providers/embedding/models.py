"""Schemas for the Embedding Provider abstraction.

No real embedding API call is modeled here beyond its input/output shape —
this module defines configuration and result types only.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "EmbeddingProviderConfig",
    "EmbeddingVector",
    "FailedEmbeddingRequest",
    "EmbeddingChunkResult",
    "EmbeddingResult",
]


class EmbeddingProviderConfig(BaseModel):
    """Configuration for an embedding provider."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str
    model: str
    timeout: float = 10.0
    max_retries: int = Field(default=2, ge=0)
    retry_backoff_seconds: float = Field(default=1.0, ge=0)


class EmbeddingVector(BaseModel):
    """A single computed embedding."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    vector: list[float]
    model: str
    dimensions: int


class FailedEmbeddingRequest(BaseModel):
    """A record of one request that failed even after retries."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    error: str
    attempts: int


class EmbeddingChunkResult(BaseModel):
    """The outcome of embedding one EmbeddingChunk."""

    model_config = ConfigDict(extra="forbid")

    chunk_index: int
    vectors: list[EmbeddingVector] = Field(default_factory=list)
    failed_requests: list[FailedEmbeddingRequest] = Field(default_factory=list)


class EmbeddingResult(BaseModel):
    """The output of BaseEmbeddingProvider.generate()."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str
    generated_at: datetime
    model: str
    chunk_results: list[EmbeddingChunkResult] = Field(default_factory=list)
    success: bool
    total_requested: int
    total_succeeded: int
    total_failed: int
