"""Schemas for the Evidence Engine.

EvidenceGraph organizes deterministic evidence references — record
provenance and entity linkage only. No reasoning, summarization, or
prediction is modeled here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["EvidenceItem", "EvidenceGraph"]


class EvidenceItem(BaseModel):
    """One piece of evidence, traceable to exactly one KnowledgeRecord.

    `linked_companies`/`linked_sectors`/`linked_countries`/`linked_themes`
    are the names of entities this item's own text matches — references
    only, not the entities' full detection data.
    """

    model_config = ConfigDict(extra="forbid")

    record_id: str
    source: str | None = None
    provider: str | None = None
    url: str | None = None
    published_at: str | None = None
    title: str | None = None
    linked_companies: list[str] = Field(default_factory=list)
    linked_sectors: list[str] = Field(default_factory=list)
    linked_countries: list[str] = Field(default_factory=list)
    linked_themes: list[str] = Field(default_factory=list)


class EvidenceGraph(BaseModel):
    """The output of EvidenceEngine.build_graph(): evidence references only."""

    model_config = ConfigDict(extra="forbid")

    items: list[EvidenceItem] = Field(default_factory=list)
    total_records_processed: int
