"""CategoryIntelligenceReport — one category's LLM-generated narrative
interpretation of its own already-ranked, already-persisted `RankedAsset`s.

Deliberately NOT added to `app.global_markets.models` (that module stays
an import-cycle-free leaf — see `IntelligenceRun`'s own docstring). Lives
alongside `ranked_asset.py` for the same reason.

Every field here is produced by interpreting already-computed,
deterministic data — never by ranking or arithmetic (that boundary is the
explicit product requirement both `GlobalMarketsResearchAgent` and
`PennyMicrocapIntelligenceAgent`, Phase 3, are built to respect). A
report's `asset_commentaries` may only reference tickers/ranks that were
actually present in the `RankedAsset`s it was generated from — see
`validate_commentaries_are_grounded` below, the anti-hallucination check
both agents run before accepting an LLM response.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.global_markets.models import ReportCategory
from app.global_markets.ranked_asset import RankedAsset

__all__ = [
    "AssetCommentary",
    "CategoryNarrative",
    "CategoryIntelligenceReport",
    "UngroundedCommentaryError",
    "validate_commentaries_are_grounded",
]


class AssetCommentary(BaseModel):
    """One short, ticker-specific interpretive note over an already-ranked asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str = Field(min_length=1)
    rank: int = Field(gt=0)
    commentary: str = Field(min_length=1)


class CategoryNarrative(BaseModel):
    """The raw, LLM-produced shape — everything the model is asked to
    generate and nothing else. `run_id`/`category`/`provider`/`model`/
    `generated_at` are added afterward by the calling agent to build a
    `CategoryIntelligenceReport`; the LLM never sees or controls those.

    `risk_note` is optional here (a main-category report may reasonably
    have none); `PennyMicrocapIntelligenceAgent` enforces its own,
    stricter "risk_note must be present" business rule on top of this
    shape — see that agent's own `_parse_narrative`.
    """

    model_config = ConfigDict(extra="forbid")

    overall_summary: str = Field(min_length=1)
    asset_commentaries: tuple[AssetCommentary, ...] = Field(default_factory=tuple)
    risk_note: str | None = None


class CategoryIntelligenceReport(BaseModel):
    """One category's persisted narrative report for one `IntelligenceRun`.

    One row per `(run_id, category)` — mirrors `RankedAsset`'s own
    per-run-per-category persistence granularity, so a report can always
    be looked up alongside the `RankedAsset`s it was generated from.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    category: ReportCategory
    generated_at: datetime
    overall_summary: str = Field(min_length=1)
    asset_commentaries: tuple[AssetCommentary, ...] = Field(default_factory=tuple)
    risk_note: str | None = None
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class UngroundedCommentaryError(Exception):
    """Raised when an `AssetCommentary` references a ticker/rank pair that
    wasn't actually present in the `RankedAsset`s the LLM was given —
    a hallucinated reference, never silently accepted."""


def validate_commentaries_are_grounded(
    commentaries: tuple[AssetCommentary, ...], ranked_assets: tuple[RankedAsset, ...]
) -> None:
    """Raise `UngroundedCommentaryError` if any commentary's `(ticker, rank)`
    doesn't exactly match one of `ranked_assets`'s own `(ticker, rank)`
    pairs — the one anti-hallucination check both Phase 3 agents run
    before accepting an LLM response as a valid report."""
    known_pairs = {(asset.snapshot.ticker, asset.rank) for asset in ranked_assets}
    for commentary in commentaries:
        if (commentary.ticker, commentary.rank) not in known_pairs:
            raise UngroundedCommentaryError(
                f"Commentary references ticker={commentary.ticker!r} rank={commentary.rank!r}, "
                "which was not among the ranked assets supplied to the LLM."
            )
