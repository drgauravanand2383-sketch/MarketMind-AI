"""Translates between RelationalRecord/KnowledgeRecord and the PostgreSQL ORM model.

Purely structural mapping in both directions — no business logic. The only
non-trivial step is a best-effort date parse used solely to populate an
indexed column for date-range search; the original, unparsed
`published_at` string is always preserved unchanged as the source of
truth, matching KnowledgeRecord's existing contract.
"""

from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime

from app.repositories.knowledge.models import KnowledgeRecord
from app.repositories.knowledge.postgres.models import KnowledgeRecordModel
from app.services.knowledge_ingestion.models import RelationalRecord

__all__ = ["parse_published_at", "relational_record_to_model", "model_to_knowledge_record"]


def parse_published_at(published_at: str | None) -> datetime | None:
    """Best-effort parse of a raw published_at string into a datetime.

    Used only to populate an indexed column for date-range search; the
    raw string itself is never modified or replaced. Returns None if
    `published_at` is missing or not in a recognizable format — this is
    an indexing aid, not a guarantee.
    """
    if not published_at:
        return None
    try:
        return parsedate_to_datetime(published_at)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(published_at)
    except ValueError:
        return None


def _resolve_source(record: RelationalRecord) -> str | None:
    """Same fallback chain as EvidenceEngine: feed_title, then source, then provider."""
    metadata = record.source_metadata
    return metadata.get("feed_title") or metadata.get("source") or record.source_provider_id


def relational_record_to_model(record: RelationalRecord) -> KnowledgeRecordModel:
    """Map a RelationalRecord into a KnowledgeRecordModel ready to persist."""
    return KnowledgeRecordModel(
        id=record.id,
        title=record.title,
        summary=record.summary,
        url=record.url,
        published_at=record.published_at,
        published_at_parsed=parse_published_at(record.published_at),
        source_provider_id=record.source_provider_id,
        source=_resolve_source(record),
        source_metadata=record.source_metadata,
        raw=record.raw,
    )


def model_to_knowledge_record(model: KnowledgeRecordModel) -> KnowledgeRecord:
    """Map a KnowledgeRecordModel row into a KnowledgeRecord."""
    return KnowledgeRecord(
        id=model.id,
        title=model.title,
        text=model.summary,
        url=model.url,
        published_at=model.published_at,
        source_provider_id=model.source_provider_id,
        metadata=model.source_metadata,
    )
