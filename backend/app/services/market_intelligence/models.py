"""Schemas for the Market Intelligence Engine.

MarketIntelligence is produced entirely through deterministic keyword and
frequency-based rules — no LLM call, no sentiment analysis, no
stock-movement prediction, and no recommendation is modeled anywhere here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["EntityMention", "Theme", "NewsGroup", "MarketIntelligence"]


class EntityMention(BaseModel):
    """A detected entity (company, sector, or country) with its supporting evidence."""

    model_config = ConfigDict(extra="forbid")

    name: str
    mention_count: int
    supporting_record_ids: list[str] = Field(default_factory=list)


class Theme(BaseModel):
    """A recurring keyword detected across multiple records."""

    model_config = ConfigDict(extra="forbid")

    keyword: str
    occurrence_count: int
    supporting_record_ids: list[str] = Field(default_factory=list)


class NewsGroup(BaseModel):
    """A cluster of related news records, grouped by a shared detected entity."""

    model_config = ConfigDict(extra="forbid")

    group_key: str
    record_ids: list[str] = Field(default_factory=list)
    confidence_score: float


class MarketIntelligence(BaseModel):
    """The output of MarketIntelligenceEngine.analyze()."""

    model_config = ConfigDict(extra="forbid")

    total_records_analyzed: int
    groups: list[NewsGroup] = Field(default_factory=list)
    companies: list[EntityMention] = Field(default_factory=list)
    sectors: list[EntityMention] = Field(default_factory=list)
    countries: list[EntityMention] = Field(default_factory=list)
    themes: list[Theme] = Field(default_factory=list)
    unmatched_record_ids: list[str] = Field(default_factory=list)
