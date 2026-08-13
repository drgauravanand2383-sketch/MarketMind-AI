"""Schemas for CompanyResearchAgent (AGT-004).

CompanyResearchReport is assembled deterministically from already-computed
EvidenceGraph, MarketIntelligence, and RelationshipGraph data. No field
here represents a prediction or recommendation — `key_risks` specifically
models data-quality/coverage limitations of the report itself, never a
market or price risk assessment.

Sprint 39 note: `CompanyResearchNarrative`/`CompanyResearchReport.narrative`
are the one, minimal, additive schema change this sprint's LLM integration
required ("do not change the schema unless absolutely required" — see
agent.py's module docstring for the justification). Every other field on
every other model in this file is unchanged from the deterministic
version: still computed only from retrieved evidence via the existing
engines, never touched by the LLM.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CompanyResearchRequest",
    "CompanyOverview",
    "NewsReference",
    "MarketIntelligenceSummary",
    "RelationshipReference",
    "SectorExposure",
    "CountryExposure",
    "ThemeExposure",
    "EvidenceReference",
    "ConfidenceSummary",
    "RiskFlag",
    "CompanyResearchNarrative",
    "CompanyResearchReport",
]


class CompanyResearchRequest(BaseModel):
    """Input to CompanyResearchAgent.run()."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    ticker: str | None = None
    include_relationships: bool = True
    include_evidence: bool = True


class CompanyOverview(BaseModel):
    """Section 1: Company Overview."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    ticker: str | None = None
    matched: bool
    entity_recognized: bool
    mention_count: int
    supporting_record_ids: list[str] = Field(default_factory=list)


class NewsReference(BaseModel):
    """One item in Section 2: Latest News."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    title: str | None = None
    url: str | None = None
    published_at: str | None = None
    source: str | None = None


class MarketIntelligenceSummary(BaseModel):
    """Section 3: Market Intelligence."""

    model_config = ConfigDict(extra="forbid")

    mention_count: int
    group_confidence: float | None = None
    supporting_record_ids: list[str] = Field(default_factory=list)


class RelationshipReference(BaseModel):
    """One item in Section 4: Relationship Analysis."""

    model_config = ConfigDict(extra="forbid")

    related_id: str
    related_label: str
    relationship_type: str
    weight: int


class SectorExposure(BaseModel):
    """One item in Section 5: Sector Analysis."""

    model_config = ConfigDict(extra="forbid")

    sector: str
    weight: int


class CountryExposure(BaseModel):
    """One item in Section 6: Country Exposure."""

    model_config = ConfigDict(extra="forbid")

    country: str
    weight: int


class ThemeExposure(BaseModel):
    """One recurring theme whose evidence overlaps this company's own supporting records.

    Added to support portfolio-level "common themes" aggregation
    (PortfolioIntelligenceAgent, AGT-005); not one of the original nine
    sections, but a minimal, additive extension of Section 3.
    """

    model_config = ConfigDict(extra="forbid")

    keyword: str
    occurrence_count: int


class EvidenceReference(BaseModel):
    """One item in Section 7: Supporting Evidence."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    source: str | None = None
    provider: str | None = None
    url: str | None = None
    published_at: str | None = None
    title: str | None = None


class ConfidenceSummary(BaseModel):
    """Section 8: Confidence Summary."""

    model_config = ConfigDict(extra="forbid")

    overall_confidence: float
    supporting_record_count: int
    basis: str


class RiskFlag(BaseModel):
    """One item in Section 9: Key Risks.

    A deterministic data-quality/coverage limitation of this report —
    never a market, price, or investment risk assessment.
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    description: str


class CompanyResearchNarrative(BaseModel):
    """The LLM-generated, evidence-grounded narrative analysis (Sprint 39).

    Produced by CompanyResearchAgent's LLM step, reasoning only over the
    evidence/relationships/market intelligence supplied in its prompt —
    never over external knowledge, and never over anything not already
    present in the deterministic sections of the same report. `None` on
    `CompanyResearchReport.narrative` means no LLM call was made at all
    (an unmatched company / no retrieved evidence to ground it in), not a
    failure — the agent never lets an LLM reason without evidence.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    key_findings: list[str] = Field(default_factory=list)
    risk_commentary: str | None = None


class CompanyResearchReport(BaseModel):
    """The output of CompanyResearchAgent.run(): all nine required sections.

    `narrative` (Sprint 39) is purely additive — every other field is
    computed exactly as before, deterministically, from retrieved
    evidence via the existing engines.
    """

    model_config = ConfigDict(extra="forbid")

    request: CompanyResearchRequest
    generated_at: datetime
    company_overview: CompanyOverview
    latest_news: list[NewsReference] = Field(default_factory=list)
    market_intelligence: MarketIntelligenceSummary
    relationship_analysis: list[RelationshipReference] = Field(default_factory=list)
    sector_analysis: list[SectorExposure] = Field(default_factory=list)
    country_exposure: list[CountryExposure] = Field(default_factory=list)
    theme_analysis: list[ThemeExposure] = Field(default_factory=list)
    supporting_evidence: list[EvidenceReference] = Field(default_factory=list)
    confidence_summary: ConfidenceSummary
    key_risks: list[RiskFlag] = Field(default_factory=list)
    narrative: CompanyResearchNarrative | None = None
