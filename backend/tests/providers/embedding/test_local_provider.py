"""Unit tests for LocalEmbeddingProvider.

Every test injects a fake `embedding_function_factory` — no real chromadb
model is ever loaded or downloaded here, per this milestone's "no live
internet access in automated tests" constraint.
"""

from __future__ import annotations

import asyncio
from datetime import UTC

from app.providers.embedding.local import LocalEmbeddingProvider
from app.providers.embedding.models import EmbeddingProviderConfig
from app.services.embedding.models import EmbeddingBatch, EmbeddingBatchMetadata, EmbeddingChunk, EmbeddingRequest


def _config(**overrides: object) -> EmbeddingProviderConfig:
    defaults: dict[str, object] = {"provider_id": "local", "model": "test-model"}
    defaults.update(overrides)
    return EmbeddingProviderConfig(**defaults)


def _fake_factory(vector: list[float] | None = None) -> tuple[object, list[list[str]]]:
    """A fake embedding-function factory recording every call it receives."""
    vector = vector if vector is not None else [0.1, 0.2, 0.3]
    calls: list[list[str]] = []

    def factory() -> object:
        def embed(texts: list[str]) -> list[list[float]]:
            calls.append(texts)
            return [vector for _ in texts]

        return embed

    return factory, calls


async def test_embed_one_returns_a_vector_from_the_injected_function() -> None:
    factory, calls = _fake_factory([1.0, 2.0, 3.0])
    provider = LocalEmbeddingProvider(_config(), embedding_function_factory=factory)

    vector = await provider.embed_one(EmbeddingRequest(document_id="doc-1", text="Apple Inc. news"))

    assert vector == [1.0, 2.0, 3.0]
    # First call on a cold provider warms the model (see
    # `_get_embedding_function`'s own docstring) before embedding the
    # real request — the warmup text precedes the real one, never after.
    assert calls == [["marketmind embedding provider warmup"], ["Apple Inc. news"]]


async def test_embed_one_is_deterministic_for_the_same_input() -> None:
    factory, _ = _fake_factory([0.5, 0.25])
    provider = LocalEmbeddingProvider(_config(), embedding_function_factory=factory)

    first = await provider.embed_one(EmbeddingRequest(document_id="doc-1", text="same text"))
    second = await provider.embed_one(EmbeddingRequest(document_id="doc-2", text="same text"))

    assert first == second


async def test_embedding_function_is_constructed_lazily_and_cached() -> None:
    construction_count = 0

    def factory() -> object:
        nonlocal construction_count
        construction_count += 1
        return lambda texts: [[0.0] for _ in texts]

    provider = LocalEmbeddingProvider(_config(), embedding_function_factory=factory)
    assert construction_count == 0  # never called at __init__ time

    await provider.embed_one(EmbeddingRequest(document_id="doc-1", text="a"))
    await provider.embed_one(EmbeddingRequest(document_id="doc-2", text="b"))

    assert construction_count == 1  # constructed once, reused across calls


async def test_health_check_true_when_embedding_function_constructs_successfully() -> None:
    factory, _ = _fake_factory()
    provider = LocalEmbeddingProvider(_config(), embedding_function_factory=factory)

    assert await provider.health_check() is True


async def test_health_check_false_when_construction_raises() -> None:
    def failing_factory() -> object:
        raise RuntimeError("model cache is corrupt")

    provider = LocalEmbeddingProvider(_config(), embedding_function_factory=failing_factory)

    assert await provider.health_check() is False


async def test_health_check_does_not_call_the_embedding_function_itself() -> None:
    calls: list[list[str]] = []

    def factory() -> object:
        def embed(texts: list[str]) -> list[list[float]]:
            calls.append(texts)
            return [[0.0] for _ in texts]

        return embed

    provider = LocalEmbeddingProvider(_config(), embedding_function_factory=factory)

    await provider.health_check()

    assert calls == []  # constructed, but never invoked


async def test_generate_integrates_with_the_base_class_batch_orchestration() -> None:
    """End-to-end through BaseEmbeddingProvider.generate() — confirms
    LocalEmbeddingProvider plugs into the already-tested batching/retry
    machinery correctly, not just its own embed_one() in isolation."""
    from datetime import datetime

    factory, _ = _fake_factory([9.0])
    provider = LocalEmbeddingProvider(_config(), embedding_function_factory=factory)
    chunk = EmbeddingChunk(
        chunk_index=0,
        requests=[
            EmbeddingRequest(document_id="doc-1", text="Apple Inc. earnings"),
            EmbeddingRequest(document_id="doc-2", text="Microsoft cloud growth"),
        ],
    )
    batch = EmbeddingBatch(
        chunks=[chunk],
        batch_metadata=EmbeddingBatchMetadata(
            batch_id="batch-1",
            created_at=datetime.now(UTC),
            total_documents_received=2,
            accepted_count=2,
            max_batch_size=100,
            chunk_count=1,
        ),
    )

    result = await provider.generate(batch)

    assert result.success is True
    assert result.total_succeeded == 2
    assert {vector.document_id for vector in result.chunk_results[0].vectors} == {"doc-1", "doc-2"}


# --- Concurrent cold-start construction (real bug, live-observed) ---------------------------------
#
# `BaseEmbeddingProvider.generate()` fires every request in a chunk
# concurrently (`asyncio.gather`, up to `EmbeddingService.DEFAULT_MAX_BATCH_SIZE`
# = 100 in production). Before `_get_embedding_function`'s lock existed, a
# cold provider let every one of those concurrent callers race the lazy
# singleton check-then-set, each independently constructing (and, for the
# real ChromaDB default, independently triggering the one-time on-disk
# model download for) its own embedding function. Live-observed: a
# 130-article ingestion run against a freshly restarted container produced
# 95/130 embedding failures. These tests reproduce the race with a fake,
# artificially slow factory and confirm it can no longer happen.


def _slow_fake_factory(delay_seconds: float = 0.05) -> tuple[object, list[int]]:
    """A fake factory that sleeps (a real OS-thread sleep, since
    `_get_embedding_function` runs it via `asyncio.to_thread`) before
    "constructing" — simulating a real, slow model load/download and
    deliberately widening the race window so that, without the fix's
    lock, many concurrent `embed_one()` callers would reliably all pass
    the `self._embedding_function is None` check before the first one
    finishes and assigns it. `construction_count` records one entry per
    construction, so the test can assert it happened exactly once
    regardless of how many callers raced for it — with the lock in
    place, this is deterministic (not a matter of getting lucky with
    scheduling); without it, this same test would flake or fail.
    """
    import time

    construction_count: list[int] = []

    def factory() -> object:
        time.sleep(delay_seconds)
        construction_count.append(1)

        def embed(texts: list[str]) -> list[list[float]]:
            return [[0.0] for _ in texts]

        return embed

    return factory, construction_count


async def test_concurrent_embed_one_calls_on_a_cold_provider_construct_exactly_once() -> None:
    """The exact scenario `BaseEmbeddingProvider.generate()` creates in
    production: many `embed_one()` calls in flight simultaneously against
    a provider that has never yet constructed its embedding function."""
    factory, construction_count = _slow_fake_factory()
    provider = LocalEmbeddingProvider(_config(), embedding_function_factory=factory)

    requests = [EmbeddingRequest(document_id=f"doc-{i}", text=f"text {i}") for i in range(25)]
    results = await asyncio.gather(*(provider.embed_one(r) for r in requests))

    assert len(construction_count) == 1  # never raced, never duplicated
    assert len(results) == 25
    assert all(vector == [0.0] for vector in results)


async def test_concurrent_embed_one_calls_all_still_return_correct_results() -> None:
    """Not just "constructed once" — every concurrent caller must still
    get back its own correctly embedded vector, not one that was dropped
    or overwritten by a losing racer."""
    factory, _ = _fake_factory([7.0, 8.0])
    provider = LocalEmbeddingProvider(_config(), embedding_function_factory=factory)

    requests = [EmbeddingRequest(document_id=f"doc-{i}", text=f"text {i}") for i in range(10)]
    results = await asyncio.gather(*(provider.embed_one(r) for r in requests))

    assert results == [[7.0, 8.0]] * 10


async def test_generate_through_a_full_100_request_chunk_constructs_the_function_exactly_once() -> None:
    """End-to-end through the real `BaseEmbeddingProvider.generate()`
    orchestration, at production's own real chunk size — not a
    hand-rolled `asyncio.gather` in the test, the actual code path that
    produced the live 95/130 failure."""
    from datetime import datetime

    factory, construction_count = _slow_fake_factory()
    provider = LocalEmbeddingProvider(_config(), embedding_function_factory=factory)
    chunk = EmbeddingChunk(
        chunk_index=0,
        requests=[EmbeddingRequest(document_id=f"doc-{i}", text=f"text {i}") for i in range(100)],
    )
    batch = EmbeddingBatch(
        chunks=[chunk],
        batch_metadata=EmbeddingBatchMetadata(
            batch_id="batch-cold-start",
            created_at=datetime.now(UTC),
            total_documents_received=100,
            accepted_count=100,
            max_batch_size=100,
            chunk_count=1,
        ),
    )

    result = await provider.generate(batch)

    assert len(construction_count) == 1
    assert result.success is True
    assert result.total_succeeded == 100
    assert result.total_failed == 0
