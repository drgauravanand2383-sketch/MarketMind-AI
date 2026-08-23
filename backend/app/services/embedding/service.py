"""Embedding Service.

Accepts VectorDocument objects and converts them into EmbeddingRequest
objects, grouped into size-bounded chunks. This service performs no API
calls, no vector storage, no AI inference, and no persistence — it only
validates and batches requests for a future embedding step.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.services.embedding.models import (
    EmbeddingBatch,
    EmbeddingBatchMetadata,
    EmbeddingChunk,
    EmbeddingRequest,
    RejectedDocument,
    RejectionReason,
)
from app.services.knowledge_ingestion.models import VectorDocument

__all__ = ["EmbeddingService", "DEFAULT_MAX_BATCH_SIZE"]

DEFAULT_MAX_BATCH_SIZE = 100


class EmbeddingService:
    """Converts VectorDocuments into batched EmbeddingRequests, without performing any I/O."""

    def __init__(self, max_batch_size: int = DEFAULT_MAX_BATCH_SIZE) -> None:
        """Initialize the service.

        Args:
            max_batch_size: The maximum number of EmbeddingRequests per chunk.

        Raises:
            ValueError: If max_batch_size is not a positive integer.
        """
        if max_batch_size < 1:
            raise ValueError("max_batch_size must be a positive integer")
        self._max_batch_size = max_batch_size

    def prepare_batch(self, documents: list[VectorDocument]) -> EmbeddingBatch:
        """Validate, convert, and chunk VectorDocuments into an EmbeddingBatch.

        Args:
            documents: The VectorDocuments to prepare (e.g. from
                KnowledgeIngestionService.prepare_batch().vector_documents).

        Returns:
            An EmbeddingBatch of size-bounded chunks, plus metadata
            describing what was accepted and what was rejected. Documents
            are never silently dropped.
        """
        requests: list[EmbeddingRequest] = []
        rejected_documents: list[RejectedDocument] = []
        seen_ids: set[str] = set()

        for index, document in enumerate(documents):
            rejection = self._validate(document, index, seen_ids)
            if rejection is not None:
                rejected_documents.append(rejection)
                continue

            seen_ids.add(document.id)
            requests.append(
                EmbeddingRequest(
                    document_id=document.id, text=document.text, metadata=document.metadata
                )
            )

        chunks = self._chunk(requests)

        metadata = EmbeddingBatchMetadata(
            batch_id=str(uuid.uuid4()),
            created_at=datetime.now(UTC),
            total_documents_received=len(documents),
            accepted_count=len(requests),
            rejected_documents=rejected_documents,
            max_batch_size=self._max_batch_size,
            chunk_count=len(chunks),
        )

        return EmbeddingBatch(chunks=chunks, batch_metadata=metadata)

    def _validate(
        self, document: VectorDocument, index: int, seen_ids: set[str]
    ) -> RejectedDocument | None:
        """Check whether `document` is eligible for embedding."""
        if not document.id:
            return RejectedDocument(
                document_index=index, document_id=document.id, reason=RejectionReason.MISSING_ID
            )
        if not document.text or not document.text.strip():
            return RejectedDocument(
                document_index=index, document_id=document.id, reason=RejectionReason.EMPTY_TEXT
            )
        if document.id in seen_ids:
            return RejectedDocument(
                document_index=index, document_id=document.id, reason=RejectionReason.DUPLICATE_ID
            )
        return None

    def _chunk(self, requests: list[EmbeddingRequest]) -> list[EmbeddingChunk]:
        """Split `requests` into chunks no larger than `max_batch_size`, in order."""
        chunks: list[EmbeddingChunk] = []
        for chunk_index, start in enumerate(range(0, len(requests), self._max_batch_size)):
            chunk_requests = requests[start : start + self._max_batch_size]
            chunks.append(EmbeddingChunk(chunk_index=chunk_index, requests=chunk_requests))
        return chunks
