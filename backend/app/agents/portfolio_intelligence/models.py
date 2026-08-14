"""Schemas for PortfolioIntelligenceAgent (AGT-005).

Sprint 40 note: this file holds two generations of models, both live:

- The pre-Sprint-40 set (`Holding`, `PortfolioResearchRequest`,
  `PortfolioOverview`, `HoldingSummary`, `SectorOverlap`, `CountryOverlap`,
  `CommonTheme`, `SharedRelationship`, `PortfolioEvidenceReference`,
  `HoldingConfidence`, `PortfolioConfidenceSummary`, `DataQualityFlag`,
  `PortfolioResearchReport`) — kept unchanged because
  `report_builder.py` (untouched, out of this sprint's file list) still
  builds and returns exactly these types, and this sprint's own agent
  reuses that deterministic aggregation logic directly rather than
  duplicating it ("reuse existing infrastructure wherever possible").
  `PortfolioOverview`, `SectorOverlap`, `PortfolioEvidenceReference`, and
  `DataQualityFlag` are reused as-is on the new report too, below.
- The Sprint 40 set (`PortfolioCompanyRequest`, `PortfolioIntelligenceRequest`,
  `CompanySummary`, `PortfolioNarrative`, `PortfolioIntelligenceReport`) —
  the actual input/output of this sprint's agent.

No field on either generation represents an investment recommendation, a
buy/sell/hold judgment, or a price target — `data_quality`/
`data_quality_notes` specifically model data-quality/coverage limitations,
never a market or price risk assessment.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.agents.company_research.models import CompanyResearchReport
from app.services.portfolio_market_snapshot.models import PortfolioMarketSnapshot

__all__ = [
    # Pre-Sprint-40 (still used internally via report_builder.py)
    "Holding",
    "PortfolioResearchRequest",
    "PortfolioOverview",
    "HoldingSummary",
    "SectorOverlap",
    "CountryOverlap",
    "CommonTheme",
    "SharedRelationship",
    "PortfolioEvidenceReference",
    "HoldingConfidence",
    "PortfolioConfidenceSummary",
    "DataQualityFlag",
    "PortfolioResearchReport",
    # Sprint 40
    "PortfolioCompanyRequest",
    "PortfolioIntelligenceRequest",
    "CompanySummary",
    "PortfolioNarrative",
    "PortfolioIntelligenceReport",
]


class Holding(BaseModel):
    """One position within a portfolio research request (pre-Sprint-40 shape)."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    ticker: str | None = None
    quantity: float | None = None
    average_price: float | None = None


class PortfolioResearchRequest(BaseModel):
    """Input to the pre-Sprint-40 `report_builder.build_portfolio_report()`."""

    model_config = ConfigDict(extra="forbid")

    portfolio_name: str
    holdings: list[Holding] = Field(default_factory=list)
    include_relationship_graph: bool = True
    include_evidence: bool = True


class PortfolioOverview(BaseModel):
    """Portfolio Overview — reused as-is on `PortfolioIntelligenceReport`."""

    model_config = ConfigDict(extra="forbid")

    portfolio_name: str
    holding_count: int
    matched_holding_count: int
    generated_at: datetime


class HoldingSummary(BaseModel):
    """One item in the pre-Sprint-40 Holdings Summary section."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    ticker: str | None = None
    quantity: float | None = None
    average_price: float | None = None
    resolved_company_name: str
    matched: bool
    entity_recognized: bool


class SectorOverlap(BaseModel):
    """Sector exposure aggregated across holdings — reused as-is on `PortfolioIntelligenceReport`."""

    model_config = ConfigDict(extra="forbid")

    sector: str
    company_names: list[str] = Field(default_factory=list)
    total_weight: int
    is_shared: bool


class CountryOverlap(BaseModel):
    """Country exposure aggregated across holdings (pre-Sprint-40 section, not carried onto the new report)."""

    model_config = ConfigDict(extra="forbid")

    country: str
    company_names: list[str] = Field(default_factory=list)
    total_weight: int
    is_shared: bool


class CommonTheme(BaseModel):
    """A recurring theme across holdings (pre-Sprint-40 section, not carried onto the new report)."""

    model_config = ConfigDict(extra="forbid")

    keyword: str
    company_names: list[str] = Field(default_factory=list)
    is_shared: bool


class SharedRelationship(BaseModel):
    """A relationship between two companies that are both holdings in this portfolio."""

    model_config = ConfigDict(extra="forbid")

    company_a: str
    company_b: str
    relationship_type: str
    weight: int


class PortfolioEvidenceReference(BaseModel):
    """One item of evidence aggregated across holdings — reused as-is on `PortfolioIntelligenceReport`."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    source: str | None = None
    provider: str | None = None
    url: str | None = None
    published_at: str | None = None
    title: str | None = None
    company_names: list[str] = Field(default_factory=list)
    is_shared: bool


class HoldingConfidence(BaseModel):
    """Per-holding confidence (pre-Sprint-40 section, not carried onto the new report)."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    overall_confidence: float
    supporting_record_count: int


class PortfolioConfidenceSummary(BaseModel):
    """Pre-Sprint-40 Confidence Summary section (not carried onto the new report)."""

    model_config = ConfigDict(extra="forbid")

    holdings: list[HoldingConfidence] = Field(default_factory=list)
    average_confidence: float
    minimum_confidence: float
    maximum_confidence: float


class DataQualityFlag(BaseModel):
    """One data-quality/coverage limitation — reused as-is on `PortfolioIntelligenceReport` (as `data_quality_notes`).

    Never an investment or market risk assessment.
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    description: str
    affected_company_count: int
    affected_companies: list[str] = Field(default_factory=list)


class PortfolioResearchReport(BaseModel):
    """The pre-Sprint-40 deterministic aggregation, still produced internally
    by `report_builder.build_portfolio_report()` and consumed by this
    sprint's agent as its deterministic backbone."""

    model_config = ConfigDict(extra="forbid")

    request: PortfolioResearchRequest
    generated_at: datetime
    portfolio_overview: PortfolioOverview
    holdings_summary: list[HoldingSummary] = Field(default_factory=list)
    company_intelligence: list[CompanyResearchReport] = Field(default_factory=list)
    sector_exposure: list[SectorOverlap] = Field(default_factory=list)
    country_exposure: list[CountryOverlap] = Field(default_factory=list)
    common_themes: list[CommonTheme] = Field(default_factory=list)
    shared_relationships: list[SharedRelationship] = Field(default_factory=list)
    evidence_summary: list[PortfolioEvidenceReference] = Field(default_factory=list)
    confidence_summary: PortfolioConfidenceSummary
    data_quality: list[DataQualityFlag] = Field(default_factory=list)


# --- Sprint 40 -----------------------------------------------------------


class PortfolioCompanyRequest(BaseModel):
    """One company entry in a Sprint 40 portfolio request.

    `weight`/`sector` are both optional, caller-supplied context — never
    fabricated by this agent, and passed through to the LLM prompt as
    user-supplied classification/allocation context, not as evidence.
    """

    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=1)
    ticker: str | None = None
    weight: float | None = Field(default=None, ge=0.0)
    sector: str | None = None


class PortfolioIntelligenceRequest(BaseModel):
    """Input to `PortfolioIntelligenceAgent.run()`."""

    model_config = ConfigDict(extra="forbid")

    portfolio_name: str = Field(min_length=1)
    companies: list[PortfolioCompanyRequest] = Field(default_factory=list)
    notes: str | None = None
    include_relationship_graph: bool = True
    include_evidence: bool = True


class CompanySummary(BaseModel):
    """One item in the Company Summaries section.

    `narrative_summary` is `CompanyResearchReport.narrative.summary`
    (Sprint 39) when CompanyResearchAgent produced one, else `None` — this
    agent never fabricates a summary CompanyResearchAgent didn't produce.
    """

    model_config = ConfigDict(extra="forbid")

    company_name: str
    ticker: str | None = None
    weight: float | None = None
    resolved_company_name: str
    matched: bool
    entity_recognized: bool
    overall_confidence: float
    narrative_summary: str | None = None


class PortfolioNarrative(BaseModel):
    """The LLM-generated, evidence-grounded narrative analysis (Sprint 40).

    Produced by PortfolioIntelligenceAgent's LLM step, reasoning only over
    the company summaries, sector exposure, relationships, and evidence
    supplied in its prompt. Never an investment recommendation, buy/sell/
    hold judgment, or price target — enforced by the system prompt
    (see prompts.py), not by validation here.
    """

    model_config = ConfigDict(extra="forbid")

    executive_summary: str = Field(min_length=1)
    concentration_observations: list[str] = Field(default_factory=list)
    relationship_observations: list[str] = Field(default_factory=list)
    notable_market_events: list[str] = Field(default_factory=list)


class PortfolioIntelligenceReport(BaseModel):
    """The output of `PortfolioIntelligenceAgent.run()`.

    `portfolio_overview`, `sector_exposure`, `evidence_summary`, and
    `data_quality_notes` are fully deterministic — computed by reusing
    `report_builder.build_portfolio_report()` unchanged, never touched by
    the LLM. `executive_summary`, `concentration_observations`,
    `relationship_observations`, and `notable_market_events` are the
    LLM-generated narrative layer; when no evidence was retrieved for any
    holding, these fall back to an honest "no data" statement / empty
    lists rather than fabricated content, and the LLM is never called.

    `market_snapshot` (Milestone 14) is additive and optional: this
    agent's `run()` never computes it — `PortfolioIntelligenceAgent` has
    no market-data dependency and none is added here (§10's own "extend
    an existing composition model rather than add another" guidance,
    applied literally: `GET /portfolio/intelligence` — the one existing
    place that already builds this report from a `Watchlist` — attaches
    it afterward via `PortfolioMarketSnapshotService`, without touching
    the agent's dependencies, prompt, or narrative logic at all). `None`
    on any report built without that extra step (e.g. a direct
    `agent.run()` call in a test or a future non-HTTP caller).
    """

    model_config = ConfigDict(extra="forbid")

    request: PortfolioIntelligenceRequest
    generated_at: datetime
    executive_summary: str
    portfolio_overview: PortfolioOverview
    company_summaries: list[CompanySummary] = Field(default_factory=list)
    sector_exposure: list[SectorOverlap] = Field(default_factory=list)
    concentration_observations: list[str] = Field(default_factory=list)
    relationship_observations: list[str] = Field(default_factory=list)
    notable_market_events: list[str] = Field(default_factory=list)
    evidence_summary: list[PortfolioEvidenceReference] = Field(default_factory=list)
    data_quality_notes: list[DataQualityFlag] = Field(default_factory=list)
    market_snapshot: PortfolioMarketSnapshot | None = None
