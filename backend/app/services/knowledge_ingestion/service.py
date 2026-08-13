"""Knowledge Ingestion Service.

Accepts a NewsCollectionResult, validates each NewsItem, and prepares two
parallel representations — vector documents (for a future embedding step)
and relational records (for future PostgreSQL persistence) — bundled into
an IngestionBatch. This service performs no I/O: no database writes, no
vector store writes, no embedding generation, and no AI summarization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.agents.news_collector.models import NewsCollectionResult, NewsItem
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

        for index, item in enumerate(collection_result.items):
            rejection = self._validate(item, index, seen_ids)
            if rejection is not None:
                rejected_items.append(rejection)
                continue

            assert item.id is not None  # guaranteed by _validate
            seen_ids.add(item.id)
            vector_documents.append(self._to_vector_document(item))
            relational_records.append(self._to_relational_record(item))

        metadata = IngestionMetadata(
            batch_id=str(uuid.uuid4()),
            ingested_at=datetime.now(timezone.utc),
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

    def _to_vector_document(self, item: NewsItem) -> VectorDocument:
        """Prepare a VectorDocument from a validated NewsItem. No embedding is generated."""
        assert item.id is not None
        text = "\n\n".join(part for part in (item.title, item.summary) if part)
        return VectorDocument(
            id=item.id,
            text=text,
            metadata={
                "title": item.title,
                "url": item.url,
                "published_at": item.published_at,
                "source_provider_id": item.source_provider_id,
            },
        )

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
