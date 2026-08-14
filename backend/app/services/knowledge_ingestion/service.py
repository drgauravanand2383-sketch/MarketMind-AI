"""Knowledge Ingestion Service.

Accepts a NewsCollectionResult, validates each NewsItem, and prepares two
parallel representations — vector documents (for a future embedding step)
and relational records (for future PostgreSQL persistence) — bundled into
an IngestionBatch. This service performs no I/O: no database writes, no
vector store writes, no embedding generation, and no AI summarization.

Milestone 12: optionally enriches each VectorDocument's metadata with an
entity resolution, via an injected `EntityResolutionService`. Still no I/O
— resolution is a pure, deterministic, in-memory computation over the
item's own title/summary text, same as every other step in this service.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.agents.news_collector.models import NewsCollectionResult, NewsItem
from app.services.entity_resolution.metadata import build_entity_metadata
from app.services.entity_resolution.models import EntityResolutionContext
from app.services.entity_resolution.service import EntityResolutionService
from app.services.knowledge_ingestion.models import (
    IngestionBatch,
    IngestionMetadata,
    RejectedItem,
    RejectionReason,
    RelationalRecord,
    VectorDocument,
)

__all__ = ["KnowledgeIngestionService"]


class KnowledgeIngestionService:
    """Prepares normalized NewsItems for knowledge ingestion, without performing any I/O."""

    def __init__(self, entity_resolver: EntityResolutionService | None = None) -> None:
        """Initialize the service.

        Args:
            entity_resolver: Optional EntityResolutionService. When None
                (the default), every VectorDocument's metadata is prepared
                exactly as before Milestone 12 (`entity_resolved: False`,
                no other entity fields) — fully backward compatible for
                any existing caller that constructs this service with no
                arguments. When provided, each item's title/summary is
                resolved and the outcome is attached to its metadata (see
                `_to_vector_document`).
        """
        self._entity_resolver = entity_resolver

    def prepare_batch(self, collection_result: NewsCollectionResult) -> IngestionBatch:
        """Validate and prepare an IngestionBatch from a NewsCollectionResult.

        Args:
            collection_result: The output of NewsCollectorAgent.run().

        Returns:
            An IngestionBatch containing vector documents, relational
            records, and ingestion metadata — including any rejected items
            and why they were rejected. Items are never silently dropped.
        """
        vector_documents: list[VectorDocument] = []
        relational_records: list[RelationalRecord] = []
        rejected_items: list[RejectedItem] = []
        seen_ids: set[str] = set()
        ingested_at = datetime.now(UTC)

        for index, item in enumerate(collection_result.items):
            rejection = self._validate(item, index, seen_ids)
            if rejection is not None:
                rejected_items.append(rejection)
                continue

            assert item.id is not None  # guaranteed by _validate
            seen_ids.add(item.id)
            vector_documents.append(self._to_vector_document(item, ingested_at))
            relational_records.append(self._to_relational_record(item))

        metadata = IngestionMetadata(
            batch_id=str(uuid.uuid4()),
            ingested_at=ingested_at,
            total_items_received=len(collection_result.items),
            accepted_count=len(vector_documents),
            rejected_items=rejected_items,
        )

        return IngestionBatch(
            vector_documents=vector_documents,
            relational_records=relational_records,
            ingestion_metadata=metadata,
        )

    def _validate(self, item: NewsItem, index: int, seen_ids: set[str]) -> RejectedItem | None:
        """Check whether `item` is eligible for ingestion.

        Returns:
            A RejectedItem describing why the item was excluded, or None if
            the item passed validation.
        """
        if not item.id:
            return RejectedItem(item_index=index, item_id=item.id, reason=RejectionReason.MISSING_ID)
        if not item.title and not item.summary:
            return RejectedItem(item_index=index, item_id=item.id, reason=RejectionReason.NO_CONTENT)
        if item.id in seen_ids:
            return RejectedItem(item_index=index, item_id=item.id, reason=RejectionReason.DUPLICATE_ID)
        return None

    def _to_vector_document(self, item: NewsItem, ingested_at: datetime) -> VectorDocument:
        """Prepare a VectorDocument from a validated NewsItem. No embedding is generated.

        Provenance: `metadata` carries everything needed to answer "where
        did this come from, when was it published, when was it ingested" —
        `published_at`/`url`/`source_provider_id` from the item itself,
        `ingested_at` recorded here.

        `entity_resolved` (Milestone 12): when no `entity_resolver` was
        injected, set to its honest "unknown" state (`False`) — matches
        this service's pre-Milestone-12 behavior exactly. When a resolver
        is injected, this is a *real*, computed value: True only when
        resolution reached HIGH or MEDIUM confidence and an entity was
        actually attached (`_entity_metadata`) — never silently guessed.
        """
        assert item.id is not None
        text = "\n\n".join(part for part in (item.title, item.summary) if part)
        metadata: dict[str, object] = {
            "title": item.title,
            "url": item.url,
            "published_at": item.published_at,
            "source_provider_id": item.source_provider_id,
            "ingested_at": ingested_at.isoformat(),
            "entity_resolved": False,
        }
        if self._entity_resolver is not None:
            metadata.update(self._entity_metadata(item))
        return VectorDocument(id=item.id, text=text, metadata=metadata)

    def _entity_metadata(self, item: NewsItem) -> dict[str, object]:
        """Resolve `item`'s title/summary to a canonical entity and shape
        the outcome into flat, Chroma-safe metadata fields via the shared
        `build_entity_metadata` (also used by
        `EntityResolutionBackfillService`, so an ingested record and a
        backfilled one are shaped identically)."""
        assert self._entity_resolver is not None
        result = self._entity_resolver.resolve(
            item.summary or "", EntityResolutionContext(title=item.title)
        )
        return build_entity_metadata(result)

    def _to_relational_record(self, item: NewsItem) -> RelationalRecord:
        """Prepare a RelationalRecord from a validated NewsItem. No database write occurs."""
        assert item.id is not None
        return RelationalRecord(
            id=item.id,
            title=item.title,
            summary=item.summary,
            url=item.url,
            published_at=item.published_at,
            source_provider_id=item.source_provider_id,
            source_metadata=item.source_metadata,
            raw=item.raw,
        )
