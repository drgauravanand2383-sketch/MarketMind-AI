"""Unit tests for EmbeddingService."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.embedding.models import RejectionReason
from app.services.embedding.service import EmbeddingService
from app.services.knowledge_ingestion.models import VectorDocument


def _document(**overrides: Any) -> VectorDocument:
    defaults: dict[str, Any] = {
        "id": "doc-1",
        "text": "Fed holds rates steady\n\nThe Federal Reserve left interest rates unchanged.",
        "metadata": {"source_provider_id": "rss", "url": "https://example.com/fed"},
    }
    defaults.update(overrides)
    return VectorDocument(**defaults)


# --- Unit tests -----------------------------------------------------------


def test_prepare_batch_converts_documents_to_requests() -> None:
    service = EmbeddingService()
    batch = service.prepare_batch([_document()])

    assert len(batch.chunks) == 1
    assert len(batch.chunks[0].requests) == 1
    request = batch.chunks[0].requests[0]
    assert request.document_id == "doc-1"
    assert request.text == _document().text


def test_prepare_batch_preserves_document_metadata() -> None:
    service = EmbeddingService()
    batch = service.prepare_batch([_document(metadata={"foo": "bar"})])

    assert batch.chunks[0].requests[0].metadata == {"foo": "bar"}


def test_batch_metadata_reflects_accepted_count() -> None:
    service = EmbeddingService()
    batch = service.prepare_batch([_document(id="a"), _document(id="b")])

    assert batch.batch_metadata.total_documents_received == 2
    assert batch.batch_metadata.accepted_count == 2
    assert batch.batch_metadata.rejected_documents == []


def test_prepare_batch_preserves_document_order() -> None:
    service = EmbeddingService()
    docs = [_document(id=f"doc-{i}") for i in range(5)]
    batch = service.prepare_batch(docs)

    all_requests = [req for chunk in batch.chunks for req in chunk.requests]
    assert [req.document_id for req in all_requests] == [f"doc-{i}" for i in range(5)]


# --- Empty batch tests ------------------------------------------------


def test_prepare_batch_with_no_documents_returns_empty_batch() -> None:
    service = EmbeddingService()
    batch = service.prepare_batch([])

    assert batch.chunks == []
    assert batch.batch_metadata.total_documents_received == 0
    assert batch.batch_metadata.accepted_count == 0
    assert batch.batch_metadata.chunk_count == 0
    assert batch.batch_metadata.rejected_documents == []


# --- Invalid document tests ------------------------------------------------


def test_document_with_empty_id_is_rejected() -> None:
    service = EmbeddingService()
    batch = service.prepare_batch([_document(id="")])

    assert batch.chunks == []
    rejected = batch.batch_metadata.rejected_documents
    assert len(rejected) == 1
    assert rejected[0].reason == RejectionReason.MISSING_ID


def test_document_with_empty_text_is_rejected() -> None:
    service = EmbeddingService()
    batch = service.prepare_batch([_document(text="")])

    assert batch.chunks == []
    rejected = batch.batch_metadata.rejected_documents
    assert len(rejected) == 1
    assert rejected[0].reason == RejectionReason.EMPTY_TEXT


def test_document_with_whitespace_only_text_is_rejected() -> None:
    service = EmbeddingService()
    batch = service.prepare_batch([_document(text="   \n  ")])

    rejected = batch.batch_metadata.rejected_documents
    assert len(rejected) == 1
    assert rejected[0].reason == RejectionReason.EMPTY_TEXT


def test_duplicate_document_id_is_rejected() -> None:
    service = EmbeddingService()
    batch = service.prepare_batch(
        [_document(id="dup"), _document(id="dup", text="Different text")]
    )

    assert batch.batch_metadata.accepted_count == 1
    rejected = batch.batch_metadata.rejected_documents
    assert len(rejected) == 1
    assert rejected[0].reason == RejectionReason.DUPLICATE_ID
    assert rejected[0].document_index == 1


def test_valid_and_invalid_documents_are_partitioned_correctly() -> None:
    service = EmbeddingService()
    batch = service.prepare_batch([_document(id="valid-1"), _document(id="")])

    assert batch.batch_metadata.total_documents_received == 2
    assert batch.batch_metadata.accepted_count == 1
    assert len(batch.batch_metadata.rejected_documents) == 1


# --- Batch size tests -----------------------------------------------------


def test_requests_are_split_into_chunks_of_max_batch_size() -> None:
    service = EmbeddingService(max_batch_size=2)
    docs = [_document(id=f"doc-{i}") for i in range(5)]

    batch = service.prepare_batch(docs)

    assert len(batch.chunks) == 3
    assert [len(chunk.requests) for chunk in batch.chunks] == [2, 2, 1]
    assert batch.batch_metadata.chunk_count == 3
    assert batch.batch_metadata.max_batch_size == 2


def test_chunk_indices_are_sequential() -> None:
    service = EmbeddingService(max_batch_size=1)
    docs = [_document(id=f"doc-{i}") for i in range(3)]

    batch = service.prepare_batch(docs)

    assert [chunk.chunk_index for chunk in batch.chunks] == [0, 1, 2]


def test_single_chunk_when_documents_fit_within_max_batch_size() -> None:
    service = EmbeddingService(max_batch_size=10)
    docs = [_document(id=f"doc-{i}") for i in range(3)]

    batch = service.prepare_batch(docs)

    assert len(batch.chunks) == 1
    assert len(batch.chunks[0].requests) == 3


def test_max_batch_size_must_be_positive() -> None:
    with pytest.raises(ValueError):
        EmbeddingService(max_batch_size=0)
