"""ChromaDB-backed implementation of BaseKnowledgeRepository.

ChromaKnowledgeRepository persists VectorDocuments into an injected
ChromaDB collection and retrieves/searches/deletes through it. It performs
no embedding computation of its own: document text is passed to the
injected collection, which relies on its own configured embedding function
(standard ChromaDB usage) since no upstream embedding-generation step
exists yet. This repository contains no business logic — only translation
between domain models and ChromaDB calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from app.repositories.knowledge.chroma.mapper import (
    chroma_get_result_to_record,
    chroma_query_result_to_search_results,
    vector_documents_to_chroma_add_kwargs,
)
from app.repositories.knowledge.models import (
    DeleteResult,
    KnowledgeRecord,
    SaveResult,
    SearchQuery,
    SearchResult,
)
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.services.embedding.models import EmbeddingBatch
from app.services.knowledge_ingestion.models import IngestionBatch

__all__ = ["ChromaCollection", "ChromaKnowledgeRepository"]


class ChromaCollection(Protocol):
    """The subset of ChromaDB's Collection API this repository depends on.

    Defined as a Protocol so a real chromadb.Collection, or a lightweight
    test double, can both be injected without this module importing the
    chromadb package directly.
    """

    def add(
        self,
        ids: list[str],
        documents: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None: ...

    def query(
        self,
        query_texts: list[str] | None = None,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def get(self, ids: list[str] | None = None) -> dict[str, Any]: ...

    def delete(self, ids: list[str] | None = None) -> None: ...

    def count(self) -> int: ...


class ChromaKnowledgeRepository(BaseKnowledgeRepository):
    """Persists and retrieves knowledge through an injected ChromaDB collection."""

    def __init__(self, collection: ChromaCollection) -> None:
        """Initialize the repository.

        Args:
            collection: The ChromaDB collection to read from and write to,
                injected by the caller. This repository never constructs
                its own ChromaDB client or collection.
        """
        self._collection = collection

    async def save_batch(
        self, ingestion_batch: IngestionBatch, embedding_batch: EmbeddingBatch
    ) -> SaveResult:
        """Persist `ingestion_batch.vector_documents` into the ChromaDB collection.

        `embedding_batch` is accepted to satisfy the BaseKnowledgeRepository
        contract but is not used: this repository does not compute
        embeddings, and no precomputed vectors are available on
        EmbeddingRequest yet. Document text is written as-is; the
        collection's own embedding function is responsible for vectorizing
        it. `relational_records` are not handled here — this repository is
        ChromaDB-only.
        """
        documents = ingestion_batch.vector_documents
        errors: list[str] = []

        if documents:
            try:
                add_kwargs = vector_documents_to_chroma_add_kwargs(documents)
                self._collection.add(**add_kwargs)
            except Exception as exc:  # noqa: BLE001 - surfaced in SaveResult, not raised
                errors.append(str(exc))

        return SaveResult(
            batch_id=ingestion_batch.ingestion_metadata.batch_id,
            saved_at=datetime.now(timezone.utc),
            vector_count=0 if errors else len(documents),
            relational_count=0,
            success=not errors,
            errors=errors,
        )

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Search the collection by text query, optionally filtered by metadata."""
        if not query.query_text:
            return []
        result = self._collection.query(
            query_texts=[query.query_text],
            n_results=query.top_k,
            where=query.filters or None,
        )
        return chroma_query_result_to_search_results(result)

    async def get(self, record_id: str) -> KnowledgeRecord | None:
        """Retrieve a single record by id."""
        result = self._collection.get(ids=[record_id])
        return chroma_get_result_to_record(result)

    async def delete(self, record_id: str) -> DeleteResult:
        """Delete a single record by id, reporting whether it existed."""
        existed = await self.get(record_id) is not None
        self._collection.delete(ids=[record_id])
        return DeleteResult(id=record_id, deleted=existed)

    async def health_check(self) -> bool:
        """Report whether the underlying collection is reachable."""
        try:
            self._collection.count()
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
