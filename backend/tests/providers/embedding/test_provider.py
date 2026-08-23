"""Unit tests for BaseEmbeddingProvider.

Exercises batching and retry orchestration via test-only stub providers
(no real embedding API is called anywhere in this file).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.providers.embedding.models import EmbeddingProviderConfig
from app.providers.embedding.provider import BaseEmbeddingProvider
from app.services.embedding.models import (
    EmbeddingBatch,
    EmbeddingBatchMetadata,
    EmbeddingChunk,
    EmbeddingRequest,
)


def _config(max_retries: int = 2, retry_backoff_seconds: float = 0.0) -> EmbeddingProviderConfig:
    return EmbeddingProviderConfig(
        provider_id="test-embedder",
        model="test-model",
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )


def _batch(chunks: list[EmbeddingChunk]) -> EmbeddingBatch:
    total = sum(len(chunk.requests) for chunk in chunks)
    return EmbeddingBatch(
        chunks=chunks,
        batch_metadata=EmbeddingBatchMetadata(
            batch_id="batch-1",
            created_at=datetime.now(UTC),
            total_documents_received=total,
            accepted_count=total,
            max_batch_size=100,
            chunk_count=len(chunks),
        ),
    )


class _AlwaysSucceedsProvider(BaseEmbeddingProvider):
    async def embed_one(self, request: EmbeddingRequest) -> list[float]:
        return [0.1, 0.2, 0.3]

    async def health_check(self) -> bool:
        return True


class _AlwaysFailsProvider(BaseEmbeddingProvider):
    async def embed_one(self, request: EmbeddingRequest) -> list[float]:
        raise RuntimeError("simulated embedding API failure")

    async def health_check(self) -> bool:
        return False


class _FailsThenSucceedsProvider(BaseEmbeddingProvider):
    """Fails the first `fail_times` attempts per document_id, then succeeds."""

    def __init__(self, config: EmbeddingProviderConfig, fail_times: int) -> None:
        super().__init__(config)
        self._fail_times = fail_times
        self._attempts: dict[str, int] = {}

    async def embed_one(self, request: EmbeddingRequest) -> list[float]:
        count = self._attempts.get(request.document_id, 0) + 1
        self._attempts[request.document_id] = count
        if count <= self._fail_times:
            raise RuntimeError("transient failure")
        return [1.0, 2.0]

    async def health_check(self) -> bool:
        return True


class _SelectiveFailureProvider(BaseEmbeddingProvider):
    """Fails for one specific document_id, succeeds for all others."""

    def __init__(self, config: EmbeddingProviderConfig, failing_id: str) -> None:
        super().__init__(config)
        self._failing_id = failing_id

    async def embed_one(self, request: EmbeddingRequest) -> list[float]:
        if request.document_id == self._failing_id:
            raise RuntimeError("simulated failure for this document")
        return [0.5, 0.5]

    async def health_check(self) -> bool:
        return True


def test_base_provider_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseEmbeddingProvider(_config())  # type: ignore[abstract]


async def test_generate_with_empty_batch_returns_zero_counts() -> None:
    provider = _AlwaysSucceedsProvider(_config())
    result = await provider.generate(_batch([]))

    assert result.success is True
    assert result.total_requested == 0
    assert result.total_succeeded == 0
    assert result.total_failed == 0
    assert result.chunk_results == []


async def test_generate_succeeds_for_all_requests() -> None:
    provider = _AlwaysSucceedsProvider(_config())
    chunk = EmbeddingChunk(
        chunk_index=0,
        requests=[
            EmbeddingRequest(document_id="doc-1", text="hello"),
            EmbeddingRequest(document_id="doc-2", text="world"),
        ],
    )

    result = await provider.generate(_batch([chunk]))

    assert result.success is True
    assert result.total_succeeded == 2
    assert result.total_failed == 0
    assert len(result.chunk_results) == 1
    assert len(result.chunk_results[0].vectors) == 2
    assert result.chunk_results[0].vectors[0].dimensions == 3
    assert result.chunk_results[0].vectors[0].model == "test-model"


async def test_generate_records_failed_requests_after_exhausting_retries() -> None:
    provider = _AlwaysFailsProvider(_config(max_retries=2, retry_backoff_seconds=0.0))
    chunk = EmbeddingChunk(
        chunk_index=0, requests=[EmbeddingRequest(document_id="doc-1", text="hello")]
    )

    result = await provider.generate(_batch([chunk]))

    assert result.success is False
    assert result.total_failed == 1
    assert result.total_succeeded == 0
    failed = result.chunk_results[0].failed_requests
    assert len(failed) == 1
    assert failed[0].document_id == "doc-1"
    assert failed[0].attempts == 3  # initial attempt + 2 retries


async def test_generate_recovers_after_transient_failures() -> None:
    provider = _FailsThenSucceedsProvider(
        _config(max_retries=3, retry_backoff_seconds=0.0), fail_times=2
    )
    chunk = EmbeddingChunk(
        chunk_index=0, requests=[EmbeddingRequest(document_id="doc-1", text="hello")]
    )

    result = await provider.generate(_batch([chunk]))

    assert result.success is True
    assert result.total_succeeded == 1
    assert result.chunk_results[0].vectors[0].vector == [1.0, 2.0]


async def test_generate_isolates_failure_to_one_request_within_a_chunk() -> None:
    provider = _SelectiveFailureProvider(
        _config(max_retries=0, retry_backoff_seconds=0.0), failing_id="doc-bad"
    )
    chunk = EmbeddingChunk(
        chunk_index=0,
        requests=[
            EmbeddingRequest(document_id="doc-good", text="ok"),
            EmbeddingRequest(document_id="doc-bad", text="bad"),
        ],
    )

    result = await provider.generate(_batch([chunk]))

    assert result.total_succeeded == 1
    assert result.total_failed == 1
    assert result.success is False
    vector_ids = {vector.document_id for vector in result.chunk_results[0].vectors}
    failed_ids = {failed.document_id for failed in result.chunk_results[0].failed_requests}
    assert vector_ids == {"doc-good"}
    assert failed_ids == {"doc-bad"}


async def test_generate_processes_multiple_chunks() -> None:
    provider = _AlwaysSucceedsProvider(_config())
    chunk1 = EmbeddingChunk(
        chunk_index=0, requests=[EmbeddingRequest(document_id="doc-1", text="a")]
    )
    chunk2 = EmbeddingChunk(
        chunk_index=1, requests=[EmbeddingRequest(document_id="doc-2", text="b")]
    )

    result = await provider.generate(_batch([chunk1, chunk2]))

    assert len(result.chunk_results) == 2
    assert result.chunk_results[0].chunk_index == 0
    assert result.chunk_results[1].chunk_index == 1
    assert result.total_succeeded == 2


async def test_health_check_reflects_subclass_implementation() -> None:
    assert await _AlwaysSucceedsProvider(_config()).health_check() is True
    assert await _AlwaysFailsProvider(_config()).health_check() is False
