"""Penny/micro-cap eligibility models.

`PennyStockEligibilityCriteria` is deliberately per-market and fully
configurable — never one global price threshold. A `$0.001` crypto token
is not automatically a micro-cap or undervalued asset (see
`app.global_markets.models.REPORT_CATEGORY_DEFINITIONS`'s own
`LOW_CAP_CRYPTO` "Low-Cap Crypto Discovery" naming), and "penny stock"
has no single, legally-portable cross-market definition — India, US, and
China each get their own `PennyStockEligibilityCriteria` instance with
independently configurable thresholds, per this module's own explicit
"do not treat these markets as identical" requirement.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["PennyStockMarket", "PennyStockEligibilityCriteria", "EligibilityCheckResult"]


class PennyStockMarket(StrEnum):
    """The four penny/micro-cap sub-universes — one per
    `app.global_markets.models.PENNY_MICROCAP_REPORT_CATEGORIES` entry."""

    INDIA = "INDIA"
    US = "US"
    CHINA = "CHINA"
    LOW_CAP_CRYPTO = "LOW_CAP_CRYPTO"


class PennyStockEligibilityCriteria(BaseModel):
    """One market's configurable eligibility thresholds. Every threshold
    is optional (`None` means "not enforced for this market") — Phase 1
    establishes the extensible shape; not every final threshold value is
    locked in yet (per this module's own "build the extensible
    foundation, not necessarily every final threshold rule").

    Field names are intentionally asset-class-agnostic (`min_market_cap`,
    not `min_market_cap_or_fdv`) so the same shape configures both equity
    markets (India/US/China) and `LOW_CAP_CRYPTO` — a crypto-specific
    config simply also sets `max_price=None` (never gate crypto on unit
    token price, per this module's own explicit "do not rank crypto
    primarily by token price" requirement) and leans on
    `min_market_cap`/`max_market_cap`/`min_daily_volume`/
    `max_volume_to_market_cap_ratio` instead.
    """

    model_config = ConfigDict(extra="forbid")

    market: PennyStockMarket
    max_price: float | None = Field(default=None, gt=0)
    min_market_cap: float | None = Field(default=None, gt=0)
    max_market_cap: float | None = Field(default=None, gt=0)
    min_avg_daily_traded_value: float | None = Field(default=None, gt=0)
    min_daily_volume: float | None = Field(default=None, gt=0)
    max_volume_to_market_cap_ratio: float | None = Field(default=None, gt=0)
    min_trading_history_days: int = Field(default=0, ge=0)
    exclude_suspended: bool = True
    exclude_delisted: bool = True
    max_spread_percent: float | None = Field(default=None, gt=0)
    min_data_completeness_ratio: float = Field(default=0.0, ge=0.0, le=1.0)


class EligibilityCheckResult(BaseModel):
    """The outcome of evaluating one asset against one
    `PennyStockEligibilityCriteria`. `failed_reasons` names every
    criterion the asset failed (not just the first) so a caller can
    understand a rejection fully, not guess from a single boolean.
    `data_completeness_ratio` is always reported, whether the asset
    passed or failed — how much of the criteria could actually be
    evaluated given the fields the asset's `NormalizedAssetSnapshot`
    genuinely had.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str
    market: PennyStockMarket
    eligible: bool
    failed_reasons: tuple[str, ...] = Field(default_factory=tuple)
    data_completeness_ratio: float = Field(ge=0.0, le=1.0)
