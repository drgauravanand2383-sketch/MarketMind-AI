"""Unit tests for LocalEmbeddingProvider.

Every test injects a fake `embedding_function_factory` — no real chromadb
model is ever loaded or downloaded here, per this milestone's "no live
internet access in automated tests" constraint.
"""

from __future__ import annotations

from app.providers.embedding.local import LocalEmbeddingProvider
from app.providers.embedding.models import EmbeddingProviderConfig
from app.services.embedding.models import EmbeddingRequest


def _config(**overrides: object) -> EmbeddingProviderConfig:
    defaults: dict[str, object] = {"provider_id": "local", "model": "test-model"}
    defaults.update(overrides)
    return EmbeddingProviderConfig(**defaults)


def _fake_factory(vector: list[float] = [0.1, 0.2, 0.3]) -> tuple[object, list[list[str]]]:
    """A fake embedding-function factory recording every call it receives."""
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
    assert calls == [["Apple Inc. news"]]


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
    from datetime import datetime, timezone

    from app.services.embedding.models import EmbeddingBatch, EmbeddingBatchMetadata, EmbeddingChunk

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
            created_at=datetime.now(timezone.utc),
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
