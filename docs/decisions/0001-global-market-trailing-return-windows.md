# 0001 — Global Market Intelligence: extended trailing-return windows (24H … 5Y)

**Status:** Accepted · **Date:** 2026-09-01

## Context

Global Market Intelligence (`docs/architecture/GLOBAL_MARKET_INTELLIGENCE.md`)
ranked assets on six trailing-return windows (10D / 15D / 1M / 3M / 6M /
1Y). The product owner asked for a daily, automatically-refreshed
"top per segment" view that also shows how each asset has performed
**over the past several years** — a multi-year track record, not only
recent movement. The six-window set could not express that, and the
windowed returns were not persisted at all (computed, fed to the ranking,
discarded).

## Decisions

All four points below were directed by the product owner; the
implementation follows them exactly.

1. **Window set.** *Add* four windows, keeping the existing six:
   **24H, 1W, 3Y, 5Y** — full set, shortest-to-longest:
   `24H / 1W / 10D / 15D / 1M / 3M / 6M / 1Y / 3Y / 5Y`
   (`app.global_markets.models.PerformanceWindow`).

2. **Momentum factor.** The `MOMENTUM` ranking factor compared the 10D
   daily pace vs the 1M daily pace; both are no longer the shortest
   windows. It now compares the **24H daily pace vs the 1W daily pace**
   (`_MOMENTUM_SHORT_WINDOW` / `_MOMENTUM_LONG_WINDOW` in
   `ranking/factor_scoring.py`).

3. **Ranking stays recent-focused.** The 3Y/5Y windows are **reported,
   not ranked on.** `PRICE_PERFORMANCE` blends only the sub-monthly
   cluster (`_PERFORMANCE_WINDOWS_FOR_PRICE_SCORE` = 24H / 1W / 10D / 15D
   / 1M). A spectacular multi-year return alone must not buy a higher
   Top-N score. (`SOURCE_CONFIDENCE` still counts all ten windows in its
   completeness ratio, so an asset that legitimately can't complete
   3Y/5Y honestly scores lower there.)

4. **Enable the daily run.** `GLOBAL_MARKETS_ENABLED=true` (the scheduled
   `GlobalMarketIntelligenceWorkflow`, 08:30 Asia/Kolkata). Screening was
   already enabled.

## Consequences

- **History depth.** `CategoryDataPipeline._HISTORY_LOOKBACK_DAYS`
  400 → 1900. `YahooFinanceProvider.get_price_history` no longer
  hardcodes `range=2y`; it derives the smallest covering Yahoo `range`
  token from the requested span (`_daily_range_token`) — a 5Y request
  fetches `range=10y`. The mock provider's explicit-range bar cap is now
  interval-aware (500 for intraday, 2600 for daily/weekly/monthly).
- **Persistence.** New `performance_windows` JSON column on
  `global_market_ranked_assets` (`NOT NULL DEFAULT '[]'`), migration
  `0010_ranked_asset_performance_windows` — the first incremental ALTER
  for this feature. `RankedAsset.performance_windows` carries the full
  ten `WindowedPerformance` entries verbatim from the
  `AssetPerformanceProfile`.
- **API / frontend.** `RankedAsset` responses now include
  `performance_windows` (no new endpoint). `RankedAssetTable` shows
  1Y / 3Y / 5Y columns per row and the full 24H..5Y breakdown in the
  expandable detail panel; a partial window (`is_complete=false`) is
  rendered muted with a `*` and a footnote, never as a full-window
  return.
- **`is_complete` is now load-bearing.** For crypto in particular,
  CoinGecko/Yahoo history often can't reach back 3–5 years, so those
  windows legitimately come back `is_complete=false` — honestly flagged,
  never fabricated.

## Alternatives considered (and rejected by the product owner)

- *Replace* the six windows rather than add to them — rejected; the
  sub-monthly windows still drive the ranking.
- Weight the ranking toward 3Y/5Y ("favour sustained multi-year
  winners") — rejected; ranking stays recent-focused.
