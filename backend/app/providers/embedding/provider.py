"""Abstract contract for generating embeddings from EmbeddingRequest batches.

BaseEmbeddingProvider defines the interface for calling an external
embedding API (Claude, OpenAI, Cohere, etc.) to convert prepared
EmbeddingRequests into vectors. No real API call, no storage, no ChromaDB
access, and no business logic exist here. Batch execution across chunks and
retrying individually failed requests are implemented as concrete
orchestration around the single abstract `embed_one` call, since every
embedding provider needs this behavior identically.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from app.providers.embedding.models import (
    EmbeddingChunkResult,
    EmbeddingProviderConfig,
    EmbeddingResult,
    EmbeddingVector,
    FailedEmbeddingRequest,
)
from app.services.embedding.models import EmbeddingBatch, EmbeddingRequest

__all__ = ["BaseEmbeddingProvider"]


class BaseEmbeddingProvider(ABC):
    """Abstract base class every embedding provider implementation must inherit."""

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        """Initialize the provider with its configuration.

        Args:
            config: Provider configuration, including the model name and
                retry policy.
        """
        self._config = config

    @property
    def config(self) -> EmbeddingProviderConfig:
        """This provider's configuration."""
        return self._config

    @abstractmethod
    async def embed_one(self, request: EmbeddingRequest) -> list[float]:
        """Call the embedding API for a single EmbeddingRequest and return its vector.

        Concrete subclasses implement this to call a real embedding API.
        Not implemented here — this method has no working implementation.

        Raises:
            Exception: Any failure calling the embedding API. `generate`
                retries failures raised here; this method itself should not
                implement its own retry logic.
        """
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying embedding API is configured and reachable."""
        raise NotImplementedError

    async def generate(self, batch: EmbeddingBatch) -> EmbeddingResult:
        """Generate embeddings for every request in `batch`, chunk by chunk.

        Requests within a chunk are embedded concurrently. Each request is
        retried up to `config.max_retries` times on failure before being
        recorded as failed; a failed request does not abort the rest of the
        batch or chunk.

        Args:
            batch: The EmbeddingBatch to generate vectors for.

        Returns:
            An EmbeddingResult summarizing what succeeded and what failed,
            per chunk.
        """
        chunk_results: list[EmbeddingChunkResult] = []
        total_requested = 0
        total_succeeded = 0
        total_failed = 0

        for chunk in batch.chunks:
            outcomes = await asyncio.gather(
                *(self._embed_with_retry(request) for request in chunk.requests)
            )

            vectors: list[EmbeddingVector] = []
            failed_requests: list[FailedEmbeddingRequest] = []
            for outcome in outcomes:
                total_requested += 1
                if isinstance(outcome, FailedEmbeddingRequest):
                    failed_requests.append(outcome)
                    total_failed += 1
                else:
                    vectors.append(outcome)
                    total_succeeded += 1

            chunk_results.append(
                EmbeddingChunkResult(
                    chunk_index=chunk.chunk_index,
                    vectors=vectors,
                    failed_requests=failed_requests,
                )
            )

        return EmbeddingResult(
            batch_id=batch.batch_metadata.batch_id,
            generated_at=datetime.now(UTC),
            model=self._config.model,
            chunk_results=chunk_results,
            success=total_failed == 0,
            total_requested=total_requested,
            total_succeeded=total_succeeded,
            total_failed=total_failed,
        )

    async def _embed_with_retry(
        self, request: EmbeddingRequest
    ) -> EmbeddingVector | FailedEmbeddingRequest:
        """Call `embed_one` for `request`, retrying on failure up to `max_retries` times."""
        attempts = 0
        last_error: Exception | None = None

        while attempts <= self._config.max_retries:
            attempts += 1
            try:
                vector = await self.embed_one(request)
            except Exception as exc:  # noqa: BLE001 - any embedding-call failure is retried
                last_error = exc
                if attempts <= self._config.max_retries:
                    await asyncio.sleep(self._config.retry_backoff_seconds)
                continue
            return EmbeddingVector(
                document_id=request.document_id,
                vector=vector,
                model=self._config.model,
                dimensions=len(vector),
            )

        return FailedEmbeddingRequest(
            document_id=request.document_id,
            error=str(last_error) if last_error else "unknown error",
            attempts=attempts,
        )
