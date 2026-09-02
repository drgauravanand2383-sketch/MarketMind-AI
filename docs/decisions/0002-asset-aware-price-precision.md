# 0002 — Magnitude-aware price precision for historical series

**Status:** Accepted · **Date:** 2026-09-02 · **Follows:** [0001](0001-global-market-trailing-return-windows.md)

## Context

`NormalizationService.round_price()` rounded every provider price — quote
fields **and** every historical-series OHLC bar — to a flat **2 decimal
places** (`_DEFAULT_PRICE_PRECISION = 2`). That rule was written for
cent-quoted US equities in Milestone 13 and never revisited.

Decision [0001] made Global Market Intelligence display 24H–5Y trailing
returns per asset. That exposed a latent quantization bug (review finding
**I-1**): for any instrument whose *unit price* is small, a `0.01` tick is
a large fraction of the price, so real moves round away.

Observed on the live 2026-09-01 run (`7299f692…`):

| Asset | Stored (2 dp) | Displayed return |
|---|---|---|
| `EURGBP=X` (~0.86) | `0.86` every bar | **24H / 1W / 1M / 3Y / 5Y all `0.0%`** |
| `DOGE-USD` (~$0.08) | `0.06`–`0.29` | 1W & 10D both exactly `−11.11%`; 15D & 1M both exactly `+14.29%` — single-tick artifacts |

Yahoo's chart endpoint actually returns full IEEE-754 doubles
(`0.8571699857711792`, `0.08528099954128265`) — the digits were there;
normalization was throwing them away.

The PR #1 return **mathematics** is correct and is **not** in scope here
(confirmed in the release review). This decision fixes the upstream
precision, not the window formulas.

## Decision

Historical-series prices are rounded **magnitude-aware**:

```
price ≥ $10   → 2 decimals            (unchanged — equities, JPY pairs, BTC/ETH)
price <  $10  → keep 5 significant figures, min 2 decimals
                (decimals = max(2, 5 − 1 − floor(log10(price))))
```

Examples: `325.13` · `47123.46` · `1.0834` (EUR/USD) · `0.85717` (EUR/GBP)
· `0.085281` (DOGE) · `0.00030012` (a sub-cent token).

- Implemented in `NormalizationService.round_price(value)` when called
  **without** an explicit `precision`, via `_magnitude_aware_price_decimals`.
- **Not asset-class routing.** The provider carries no asset class at the
  normalization point; price magnitude is a deterministic, robust proxy.
- **Not fabricated precision.** The rule only *keeps* digits the source
  double already holds; it never pads beyond them. It also strips a
  provider's float-noise on large values (`313.45001220703125 → 313.45`).
- **Never zeros a positive price.** Preserving 5 significant figures of a
  positive number keeps it positive by construction; a `≤ 0` value takes
  the old fixed-2dp path untouched (rejecting it is the model's
  `Field(gt=0)` job).

## Scope

- **Only `normalize_historical_series`** (its `price_precision` param now
  defaults to `None` = magnitude-aware; pass an explicit int to force
  fixed rounding). Its sole production caller is
  `YahooFinanceProvider.get_price_history`, whose sole caller is the
  Global Market Intelligence `CategoryDataPipeline`.
- **`normalize_quote` is unchanged** — still fixed 2 decimals. Company
  Research / Continuous Intelligence / Portfolio / Market Data Refresh
  quote behaviour is deliberately not altered in this change.
- **No ranking methodology change.** Once inputs carry real precision the
  existing factor math produces real signal (the audit did not prove a
  ranking change was required).

## Consequences

- **No API / schema / migration change.** Field types are unchanged
  (`float`); every persisted price already lives in a JSON column
  (arbitrary precision). Existing rows — `seed-run-older`, run
  `7299f692…` — remain readable exactly as they are.
- **A workflow run after this change produces different FX / low-price
  `WindowedPerformance` values than earlier runs.** This is an
  intentional correction. Equity categories are unchanged.
- Continuous Intelligence's own price-move detection would benefit from
  the same fix if extended to `normalize_quote`, but that is out of scope
  and its canonical universe is all large-cap today.

## Alternatives considered

- *Stop rounding history entirely* — also correct (the doubles are the
  source), but leaves provider float-noise (`313.45001220703125`) in
  stored JSON and churns every equity value cosmetically.
- *Ticker-suffix / currency routing* (`.NS`, `=X`, `-USD`) — fragile
  heuristics; magnitude alone is right in ~all real cases with zero new
  inputs.
- *Blanket 6 decimals* — explicitly rejected: keeps equity float-noise
  and is not what any instrument's source precision supports.
