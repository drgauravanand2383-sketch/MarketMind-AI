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

from datetime import UTC, datetime
from typing import Any, Protocol

from app.repositories.knowledge.chroma.mapper import (
    chroma_get_result_to_record,
    chroma_get_result_to_records,
    chroma_get_result_to_search_results,
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

    def upsert(
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

    def get(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]: ...

    def update(
        self,
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None: ...

    def delete(self, ids: list[str] | None = None) -> None: ...

    def count(self) -> int: ...


def _clean_update_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Drop None values, which ChromaDB metadata does not accept — the
    same rule `chroma.mapper._clean_metadata` applies on the `save_batch`
    path, reapplied here for `update_metadata_batch`."""
    return {key: value for key, value in metadata.items() if value is not None}


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

        Uses `upsert`, not `add`: `VectorDocument.id` is a deterministic
        function of the source article (see
        `app.agents.news_collector.normalizer`), so the same article
        reprocessed on a later ingestion run (e.g. still present in an
        RSS feed's most recent entries) arrives with the same id.
        ChromaDB's `add` raises/rejects on a duplicate id; `upsert`
        inserts-or-replaces atomically, which is what makes rerunning
        ingestion idempotent rather than erroring or duplicating records.

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
                self._collection.upsert(**add_kwargs)
            except Exception as exc:  # noqa: BLE001 - surfaced in SaveResult, not raised
                errors.append(str(exc))

        return SaveResult(
            batch_id=ingestion_batch.ingestion_metadata.batch_id,
            saved_at=datetime.now(UTC),
            vector_count=0 if errors else len(documents),
            relational_count=0,
            success=not errors,
            errors=errors,
        )

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Search the collection by text query, optionally filtered by
        metadata — or, with no query text, by metadata filters alone.

        Milestone 12: a metadata-only structured lookup (e.g.
        `KnowledgeHub.search(KnowledgeSearchFilters(company=entity_id))`,
        used by entity-aware retrieval) has no text to rank by, so it
        cannot use ChromaDB's nearest-neighbor `query()` — that requires
        `query_texts`. It uses `get(where=...)` instead, ChromaDB's own
        metadata-filter lookup with no ranking. Previously (pre-Milestone
        12) this method returned `[]` whenever `query_text` was empty
        regardless of `filters` — dead code in practice, since no record
        ever had a metadata key any filter targeted; now that entity
        resolution actually sets one (`company`), a real filter-only
        query needs this to work.
        """
        if query.query_text:
            result = self._collection.query(
                query_texts=[query.query_text],
                n_results=query.top_k,
                where=query.filters or None,
            )
            return chroma_query_result_to_search_results(result)
        if query.filters:
            result = self._collection.get(where=query.filters, limit=query.top_k)
            return chroma_get_result_to_search_results(result)
        return []

    async def get(self, record_id: str) -> KnowledgeRecord | None:
        """Retrieve a single record by id."""
        result = self._collection.get(ids=[record_id])
        return chroma_get_result_to_record(result)

    async def list_all(
        self, limit: int | None = None, offset: int | None = None
    ) -> list[KnowledgeRecord]:
        """List every record in the collection, or one page of it.

        Milestone 12: the read half of the entity-resolution backfill
        mechanism — enumerates already-ingested records so their metadata
        can be resolved and updated in place (`update_metadata_batch`).
        `limit`/`offset` support processing a large collection in bounded
        pages rather than loading everything into memory at once; omit
        both for "every record" (the common case for this deployment's
        collection sizes today).
        """
        result = self._collection.get(limit=limit, offset=offset)
        return chroma_get_result_to_records(result)

    async def update_metadata_batch(
        self, ids: list[str], metadatas: list[dict[str, Any]]
    ) -> None:
        """Replace the stored metadata for each of `ids`, leaving each
        record's document text and embedding untouched.

        Milestone 12: the write half of the backfill mechanism. Uses
        ChromaDB's own `update()` (not `upsert()`): `update()` only
        changes the fields explicitly passed (here, only `metadatas`),
        whereas `upsert()` would require re-supplying document text this
        repository never re-fetches — this milestone's own "do not
        rewrite existing article content" constraint. Each entry in
        `metadatas` fully replaces that id's stored metadata (ChromaDB
        does not merge at the key level), so callers must merge onto the
        record's existing metadata themselves before calling this — see
        `EntityResolutionBackfillService`.
        """
        if not ids:
            return
        self._collection.update(ids=ids, metadatas=[_clean_update_metadata(m) for m in metadatas])

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
