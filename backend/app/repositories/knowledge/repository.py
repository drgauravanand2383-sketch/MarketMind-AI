"""Abstract contract for persisting and retrieving knowledge.

BaseKnowledgeRepository defines the persistence and retrieval boundary for
the Knowledge Hub's storage layer. No database implementation, no ChromaDB
implementation, no SQL, and no embedding generation exist here — only the
contract every concrete repository implementation must satisfy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.repositories.knowledge.models import (
    DeleteResult,
    KnowledgeRecord,
    SaveResult,
    SearchQuery,
    SearchResult,
)
from app.services.embedding.models import EmbeddingBatch
from app.services.knowledge_ingestion.models import IngestionBatch

__all__ = ["BaseKnowledgeRepository"]


class BaseKnowledgeRepository(ABC):
    """Abstract base class every knowledge repository implementation must inherit."""

    @abstractmethod
    async def save_batch(
        self, ingestion_batch: IngestionBatch, embedding_batch: EmbeddingBatch
    ) -> SaveResult:
        """Persist a prepared IngestionBatch alongside its EmbeddingBatch.

        Args:
            ingestion_batch: Relational records and vector documents
                prepared by KnowledgeIngestionService.
            embedding_batch: Batched embedding requests prepared by
                EmbeddingService, corresponding to the same documents.

        Returns:
            A SaveResult describing what was persisted.
        """
        raise NotImplementedError

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Retrieve knowledge records matching `query`.

        Args:
            query: The search request (text query, filters, and/or top_k).

        Returns:
            A list of SearchResult records, ordered by relevance.
        """
        raise NotImplementedError

    @abstractmethod
    async def get(self, record_id: str) -> KnowledgeRecord | None:
        """Retrieve a single knowledge record by id.

        Returns:
            The matching KnowledgeRecord, or None if no record exists for `record_id`.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, record_id: str) -> DeleteResult:
        """Delete a single knowledge record by id."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backends are reachable."""
        raise NotImplementedError
