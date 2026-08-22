"""Schemas for the Knowledge Ingestion Service.

VectorDocument and RelationalRecord are prepared representations only —
neither is written anywhere by this service. IngestionBatch bundles both
alongside metadata describing what was accepted and what was rejected.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "RejectionReason",
    "RejectedItem",
    "VectorDocument",
    "RelationalRecord",
    "IngestionMetadata",
    "IngestionBatch",
]


class RejectionReason(str, Enum):
    """Why a NewsItem was excluded from an IngestionBatch."""

    MISSING_ID = "missing_id"
    NO_CONTENT = "no_content"
    DUPLICATE_ID = "duplicate_id"
    DUPLICATE_URL = "duplicate_url"
    """v1.2 Priority 6: the same article reachable via two different
    configured feeds (e.g. one Nasdaq category feed and a company IR feed
    both syndicating the same press release) commonly carries two
    different `<guid>` values, so `DUPLICATE_ID`'s exact-id check alone
    does not catch it — this reason is used when a later item's
    normalized URL matches an already-accepted item's, even though its id
    differs. See `KnowledgeIngestionService._normalized_url`."""


class RejectedItem(BaseModel):
    """A record of one NewsItem that was excluded from ingestion, and why."""

    model_config = ConfigDict(extra="forbid")

    item_index: int
    item_id: str | None
    reason: RejectionReason
    detail: str | None = None


class VectorDocument(BaseModel):
    """A document prepared for future vector storage. No embedding is generated here."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RelationalRecord(BaseModel):
    """A record prepared for future PostgreSQL storage. No database write occurs here."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None = None
    summary: str | None = None
    url: str | None = None
    published_at: str | None = None
    source_provider_id: str
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class IngestionMetadata(BaseModel):
    """Batch-level outcome of one ingestion preparation run."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str
    ingested_at: datetime
    total_items_received: int
    accepted_count: int
    rejected_items: list[RejectedItem] = Field(default_factory=list)


class IngestionBatch(BaseModel):
    """The output of KnowledgeIngestionService.prepare_batch()."""

    model_config = ConfigDict(extra="forbid")

    vector_documents: list[VectorDocument] = Field(default_factory=list)
    relational_records: list[RelationalRecord] = Field(default_factory=list)
    ingestion_metadata: IngestionMetadata
