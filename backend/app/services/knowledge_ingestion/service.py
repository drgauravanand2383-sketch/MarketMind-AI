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
from urllib.parse import urlsplit, urlunsplit

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
        seen_urls: set[str] = set()
        ingested_at = datetime.now(UTC)

        for index, item in enumerate(collection_result.items):
            rejection = self._validate(item, index, seen_ids, seen_urls)
            if rejection is not None:
                rejected_items.append(rejection)
                continue

            assert item.id is not None  # guaranteed by _validate
            seen_ids.add(item.id)
            normalized_url = self._normalized_url(item.url)
            if normalized_url is not None:
                seen_urls.add(normalized_url)
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

    def _validate(
        self, item: NewsItem, index: int, seen_ids: set[str], seen_urls: set[str]
    ) -> RejectedItem | None:
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
        # v1.2 Priority 6 (§9): a same-batch duplicate across two different
        # *configured feeds* commonly carries two different <guid> values
        # (DUPLICATE_ID above never catches it) but the same underlying
        # article URL — checked only when the item survived the id check,
        # so this never fires for two genuinely distinct articles that
        # merely lack a url.
        normalized_url = self._normalized_url(item.url)
        if normalized_url is not None and normalized_url in seen_urls:
            return RejectedItem(item_index=index, item_id=item.id, reason=RejectionReason.DUPLICATE_URL)
        return None

    @staticmethod
    def _normalized_url(url: str | None) -> str | None:
        """Lowercased scheme+host+path, query string and fragment
        stripped — the same story linked with different tracking
        parameters (`?utm_source=...`) or a trailing `#section` is still
        the same article. `None` for a blank/missing url, never treated
        as a collision with another blank url."""
        if not url or not url.strip():
            return None
        parts = urlsplit(url.strip())
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))

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
        # v1.2 Priority 6 (§5, §1 finding): `item.source_metadata` (feed
        # url/title, author, and — since this milestone — source name/
        # category/tag) was previously computed by the normalizer but
        # never actually reached the persisted vector document's own
        # metadata — only `RelationalRecord` (never written anywhere;
        # see that model's own docstring) carried it. Every Chroma-safe
        # (string/number/bool) field is copied through here so real
        # provenance ("which feed, what category") survives into the
        # record an operator or Research can actually query.
        for key in ("feed_url", "feed_title", "author", "source_name", "category", "tag"):
            value = item.source_metadata.get(key)
            if value is not None:
                metadata[key] = value
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
