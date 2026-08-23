"""Schemas for the Entity Resolution & Company Intelligence layer (Milestone 12).

Every model here is fully typed and produced deterministically — no LLM
call, no fuzzy/probabilistic matching, and no fabricated company data
anywhere in this package. `EntityResolutionResult` is intentionally
explainable: every resolution carries the method and evidence that
produced it, never an opaque score.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ConfidenceTier",
    "ResolutionMethod",
    "CompanyReference",
    "EntityCandidate",
    "EntityResolutionContext",
    "EntityResolutionResult",
    "BackfillResult",
]


class ConfidenceTier(StrEnum):
    """The confidence classification of one entity resolution.

    See `docs/architecture/ENTITY_RESOLUTION.md` §6 for the full policy
    and rationale behind each threshold.

    HIGH: safe for automatic resolution — the entity is attached.
    MEDIUM: attached, but flagged for review (`entity_needs_review`) —
        genuine evidence exists, but not enough to treat as certain.
    LOW: a candidate was found, but confidence is too low to safely
        attach it — the article is retained, unassociated.
    UNRESOLVED: no candidate was found at all.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNRESOLVED = "UNRESOLVED"


class ResolutionMethod(StrEnum):
    """Which signal produced a given EntityCandidate's match."""

    EXACT_NAME = "exact_name"
    LEGAL_NAME = "legal_name"
    ALIAS = "alias"
    TICKER = "ticker"
    NONE = "none"


class CompanyReference(BaseModel):
    """One canonical company/entity identity in the static reference set.

    This is the "canonical company representation" required by this
    milestone's own §2 — deliberately not a second/parallel company model:
    every field here is either sourced directly from, or a documented
    superset of, the same real-world facts already hardcoded in
    `app.services.market_intelligence.engine.COMPANY_KEYWORDS` (name +
    aliases), the one canonical reference set the rest of this codebase
    (MarketIntelligenceEngine, EvidenceEngine, CompanyResearchAgent's own
    `resolve_company_name`) already relies on. See
    `app.services.entity_resolution.reference_data` for how this set is
    built.
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    legal_name: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    aliases: tuple[str, ...] = Field(default_factory=tuple)


class EntityCandidate(BaseModel):
    """One candidate company match for a piece of text, fully explainable.

    `score` is a transparent [0.0, 1.0] value computed from the factors
    named in `matched_terms`/`method`/`occurrence_count`/`title_match` —
    never an opaque black-box number (this milestone's own §5 constraint).
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    canonical_name: str
    ticker: str | None = None
    method: ResolutionMethod
    score: float = Field(ge=0.0, le=1.0)
    matched_terms: tuple[str, ...] = Field(default_factory=tuple)
    occurrence_count: int = Field(default=0, ge=0)
    title_match: bool = False


class EntityResolutionContext(BaseModel):
    """Optional extra context `EntityResolutionService.resolve()` can use.

    `title` is scored separately from the rest of `text` (title mentions
    weigh more — §5's "title vs body weighting" requirement).
    `source_metadata` is accepted for forward-compatibility with §5's
    "source metadata" scoring factor; not currently used to adjust scores
    (no source-quality signal exists anywhere in this codebase to weight
    it by), but real callers may pass it and future work can start using
    it without a signature change.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    source_metadata: dict[str, str] = Field(default_factory=dict)


class EntityResolutionResult(BaseModel):
    """The output of `EntityResolutionService.resolve()`.

    `primary`/`secondary` are only populated when `confidence_tier` is
    HIGH or MEDIUM — per §6, a LOW or UNRESOLVED result never attaches an
    entity, even though `candidates` may still list what was considered
    and rejected, for transparency.
    """

    model_config = ConfigDict(extra="forbid")

    primary: EntityCandidate | None = None
    secondary: tuple[EntityCandidate, ...] = Field(default_factory=tuple)
    confidence_tier: ConfidenceTier
    candidates: tuple[EntityCandidate, ...] = Field(default_factory=tuple)
    reason: str


class BackfillResult(BaseModel):
    """The outcome of one `EntityResolutionBackfillService.run()` call.

    `records_processed` counts every existing record considered;
    `records_updated` is 0 for a `dry_run=True` call (nothing is written)
    even though every other count still reflects what *would* have
    happened — the dry-run's whole purpose is previewing that outcome.
    """

    model_config = ConfigDict(extra="forbid")

    dry_run: bool
    records_processed: int = 0
    records_updated: int = 0
    high_confidence_count: int = 0
    medium_confidence_count: int = 0
    low_confidence_count: int = 0
    unresolved_count: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
