# Global Market Intelligence

**Phase 1 (foundation) + Phase 2 (deterministic pipeline) + Phase 3
(narrative interpretation) + Phase 4 (read-only API surface) + Phase 5
(WebSocket distribution — see §13) + Phase 6a (frontend) + Phase 6b (real
per-market penny-stock eligibility criteria — see §4) + Phase 6c
(penny/micro-cap candidate discovery — see §14) + Phase 7 (extended
trailing-return windows: 24H..5Y, up from 10D..1Y — persisted on each
`RankedAsset` and surfaced in the API and frontend; see §3, §8, §12,
§15) + Phase 8 (daily-intelligence surfacing: dashboard card, "Top Picks"
tab, permission grant, 15-ticker main universes + equity penny fallback
universes — see §7, §16) are implemented.** Daily,
multi-market intelligence covering nine reporting categories across five
market regions (India, US, China, Forex, Crypto), published once daily
via a scheduled workflow, readable over `/api/v1/global-markets`,
announced in real time over the existing `/ws` framework, consumed by a
dedicated frontend section, and — once `GLOBAL_MARKET_SCREENING_ENABLED`
is turned on — populating its own four penny/micro-cap candidate
universes from real, live vendor data rather than sitting permanently
empty. See §10 for what's still genuinely missing.

**Only two AI agents exist for this feature, exactly as scoped** —
`GlobalMarketsResearchAgent` (AGT-006, the five main categories) and
`PennyMicrocapIntelligenceAgent` (AGT-007, the four penny/micro-cap
categories) — see §11. Every other component in this document — calendar
resolution, performance calculation, factor scoring, ranking, eligibility,
persistence — is a plain deterministic service. AI is responsible for
*interpretation* of already-ranked results, never for ranking or
arithmetic; both agents compute nothing.

## 1. Taxonomy

`app/global_markets/models.py` is the single source of truth. Two
orthogonal axes, deliberately kept separate:

- `MarketRegion` — a calendar/timezone concern (INDIA, US, CHINA, FOREX,
  CRYPTO). Governs which trading calendar and timezone a result's
  freshness is judged against.
- `AssetClass` — what kind of instrument (EQUITY, FOREX, CRYPTO,
  PENNY_STOCK, MICROCAP_CRYPTO).

`ReportCategory` is the nine fixed, user-facing categories, each an
explicit `(MarketRegion, AssetClass)` pair via
`REPORT_CATEGORY_DEFINITIONS` (never recomputed ad hoc): five main
Top-15 categories (`MAIN_REPORT_CATEGORIES` — India/US/China Equity,
Forex, Crypto) and four penny/micro-cap Top-20 categories
(`PENNY_MICROCAP_REPORT_CATEGORIES` — India/US/China Penny Stocks,
"Low-Cap Crypto Discovery"). Categories are never combined into one mixed
ranking.

## 2. Timezone & trading-calendar architecture (approved decisions)

**Decision 1 — no global "today".** The master scheduler fires once at
08:30 `Asia/Kolkata`, but each `ReportCategory`'s own market region
independently resolves whether its market is open, what its last
completed session was, and its own data-freshness status —
`MarketSessionResolutionService.resolve()`
(`app/global_markets/session/resolver.py`) builds one
`MarketSessionContext` per region per run. Two contexts built in the same
run are never assumed to share a `market_session_date`. Canonical
timezones (`MARKET_REGION_TIMEZONES`): India=`Asia/Kolkata`,
US=`America/New_York`, China=`Asia/Shanghai`, Forex/Crypto=`UTC` (each
with its own session-open logic — see §3). Every result carries
`source_timestamp`/`retrieved_at`/`data_freshness_status` via
`DataProvenance` (per-datapoint) and `market_timezone`/
`market_session_date`/`last_completed_session`/`as_of_timestamp` via
`MarketSessionContext` (per-market-per-run).

`MarketSessionContext.data_freshness_status` is always exactly
`LIVE`/`PREVIOUS_CLOSE`/`UNAVAILABLE` — never `STALE`. Staleness is a
*data-fetch-time* judgment (comparing a specific datapoint's
`retrieved_at` against `freshness_cutoff`), which the calendar-only
session resolver cannot know; `DataProvenance.data_freshness_status` on
each fetched/normalized value is where `STALE` would apply. This was a
design correction made during Phase 1: an earlier version marked every
ordinary weekend `STALE` by conflating wall-clock-elapsed time with
calendar closure.

**Decision 2 — no in-house global trading calendar.** Every calendar
lives behind `TradingCalendarProvider` (`app/global_markets/calendar/provider.py`),
a synchronous, deterministic, no-I/O ABC. India/US/China are backed by
real `pandas_market_calendars` calendars (`NSE`/`NYSE`/`SSE` —
`PandasMarketCalendarProvider`; live-verified before adoption). No
separate Shenzhen (SZSE) calendar exists in that library; SSE is used as
a documented, intentional proxy for both Shanghai and Shenzhen sessions.
Forex/Crypto have no exchange calendar at all and are backed by
in-house, from-scratch providers (`app/global_markets/calendar/continuous_calendar.py`):
`CryptoCalendarProvider` (every UTC day is a full session) and
`ForexCalendarProvider` (a Sun 22:00 UTC – Fri 22:00 UTC market week,
instant-based open/close arithmetic). `TradingCalendarRegistry` maps
`MarketRegion -> TradingCalendarProvider`; nothing outside the `calendar/`
package imports `pandas_market_calendars` directly.

## 3. Performance windows

`PerformanceCalculationService` (`app/global_markets/performance/engine.py`)
computes **ten** `PerformanceWindow`s per asset from an already-fetched
`HistoricalSeries` — no I/O. The set, shortest-to-longest:
**24H / 1W / 10D / 15D / 1M / 3M / 6M / 1Y / 3Y / 5Y**. Methodology is
explicit per market region, never one blanket calendar-day subtraction:

- **24H / 1W / 10D / 15D, session-based markets** (equities, forex): the
  Nth most recent *bar* (24H → 1 bar, 1W → 5 bars, 10D → 10, 15D → 15),
  not calendar-day subtraction — correct by construction because a real
  provider's daily series only contains bars for days that actually
  traded.
- **24H / 1W / 10D / 15D, crypto**: calendar-day anchored (24H → 1 day,
  1W → 7, 10D → 10, 15D → 15 — crypto trades every day).
- **1M / 3M / 6M / 1Y / 3Y / 5Y, every region**: calendar month/year
  subtraction anchored on the latest bar's date (stdlib
  `calendar.monthrange`, `_shift_months`/`_shift_years`), snapped to the
  nearest bar at-or-before the anchor.

A window that the asset's history doesn't fully cover is still reported,
with `WindowedPerformance.is_complete=False` — never silently dropped or
presented as a full-window return. The 3Y/5Y windows in particular make
this flag load-bearing: a recently-listed stock, or any asset on a
low-history provider, legitimately returns `is_complete=False` there.

**History depth**: `CategoryDataPipeline._HISTORY_LOOKBACK_DAYS` is
`1900` (≈ 5Y + weekend/holiday anchor slack), and `YahooFinanceProvider
.get_price_history` now derives its Yahoo `range` token from the
requested `[start, end]` span (`_daily_range_token`) — a 5Y request
fetches `range=10y` daily bars, not the old hardcoded `2y`. See §5.

**Price precision**: bar prices are normalized **magnitude-aware** — 2
decimals at/above $10 (equities unchanged), 5 significant figures below
it — so an FX cross rate or a sub-dollar coin's real moves are not
quantized into `0.0%` / single-tick returns. See
`docs/architecture/MARKET_DATA_ARCHITECTURE.md` §6.1 and
`docs/decisions/0002-asset-aware-price-precision.md`. A workflow run
after that change produces different (more accurate) FX / low-price
`WindowedPerformance` values than earlier runs — an intentional
correction; equity categories are unchanged.

## 4. Ranking & eligibility (Phase 1 contract, Phase 2 real scoring)

`RankingFactor` (`app/global_markets/ranking/models.py`) names twelve
possible inputs; `FactorScoringService`
(`app/global_markets/ranking/factor_scoring.py`) currently computes five
of them — `PRICE_PERFORMANCE`, `MOMENTUM`, `VOLUME_LIQUIDITY`, `RISK`
(inverted: higher = safer), `SOURCE_CONFIDENCE` — all **cross-sectionally
min-max scaled to [0, 100] relative to the other assets in the same
batch**, never against a fixed absolute threshold (no universal "good
momentum" scale spans India equities, forex pairs, and crypto).

**The ranking stays recent-focused** even though the window set now
reaches 5Y (§3): `PRICE_PERFORMANCE` blends only the sub-monthly cluster
(`_PERFORMANCE_WINDOWS_FOR_PRICE_SCORE` = 24H / 1W / 10D / 15D / 1M), and
`MOMENTUM` is the 24H daily pace minus the 1W daily pace
(`_MOMENTUM_SHORT_WINDOW` / `_MOMENTUM_LONG_WINDOW`). The 3Y/5Y windows
are **persisted and surfaced** (§8, §12, §15) so an asset's multi-year
track record is visible, but they never move the Top-N selection — a
spectacular 5Y return alone cannot buy a higher score. `SOURCE_CONFIDENCE`
does count all ten windows in its completeness ratio, so an asset that
legitimately can't complete 3Y/5Y honestly scores lower there.
`WeightedRankingEngine` (`ranking/engine.py`) combines them via a fully
configurable `RankingWeights` and ranks, tie-broken by `(-final_score,
ticker)` — deterministic and reproducible. Two default weight profiles
(`ranking/defaults.py`): `DEFAULT_MAIN_RANKING_WEIGHTS` (all five
factors) and `DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS` (deliberately
*excludes* `PRICE_PERFORMANCE`, structurally enforcing "never simply rank
by percentage return" for penny/micro-cap categories).

Penny/micro-cap eligibility (`app/global_markets/eligibility/`) is a
separate, per-market gate: `ConfigurableEligibilityProvider` evaluates a
`NormalizedAssetSnapshot` against one market's `PennyStockEligibilityCriteria`
(every threshold optional/configurable; a threshold with no data reduces
`data_completeness_ratio`, never counted as a pass or fail).
`app/global_markets/eligibility/defaults.py` (Phase 6b) configures real,
sourced default criteria per market — the US's `max_price=$5.00` is the
SEC's own Rule 3a51-1 penny-stock definition; India/China use documented
market conventions (₹20, ¥10) rather than an invented number;
`LOW_CAP_CRYPTO` is gated only by market-cap/liquidity, never unit token
price. `GlobalMarketIntelligenceWorkflow._resolve_category` wires
`eligibility_provider_for_category(category)` into `CategoryDataPipeline.run`
for every penny/micro-cap category (`None`, i.e. no filtering, for the
five main categories). **Caveat:** the live pipeline never populates
`NormalizedAssetSnapshot.market_cap`/`.bid_ask_spread_percent`/
`.is_suspended`/`.is_delisted` today (see `MarketDataNormalizer`'s own
docstring) — those specific criteria reduce `data_completeness_ratio`
but cannot yet reject an asset, until a market-cap-capable data source
is wired in.

`RiskClassification` (`ranking/classification.py`) is a deterministic
label from momentum/risk/confidence scores — never proof of fraud or
manipulation, and a high-momentum/high-risk asset is never labeled an
unqualified "best opportunity" (`STRONG_MOMENTUM_HIGH_RISK`/
`EXTREME_MOMENTUM_EXTREME_RISK` keep both halves equally visible).
`INSUFFICIENT_CONFIDENCE` is returned rather than guessing a flattering
tier when `data_confidence_score` is too low. Every threshold is a
keyword argument on `classify()` — configurable, never a buried literal.

## 5. The deterministic per-category pipeline (Phase 2)

`CategoryDataPipeline` (`app/global_markets/pipeline/category_pipeline.py`)
is the one place fetch -> normalize -> score -> (optional eligibility
filter) -> rank -> truncate-to-`top_n` happens for one category:

```
CategoryDataPipeline.run(run_id, category, universe, ranking_weights, freshness_status)
        |
        +--> MarketDataProvider.get_quote() / get_price_history(start = today - 1900d)   per ticker, isolated
        +--> MarketDataNormalizer.normalize()   -> NormalizedAssetSnapshot
        +--> [optional] PennyStockEligibilityProvider.evaluate()   -> drop ineligible
        +--> PerformanceCalculationService.calculate()   -> AssetPerformanceProfile (10 windows, 24H..5Y)
        +--> FactorScoringService.score_batch()   -> FactorScore per asset
        +--> WeightedRankingEngine.rank()   -> RankedAssetScore, truncated to top_n
        +--> [optional] classify()   -> RiskClassification (penny/micro-cap only)
        -> tuple[RankedAsset, ...]   (each carrying its full performance_windows, verbatim from the profile)
```

One ticker's fetch failure is isolated (`continue`, never abort the
batch) — the same per-item-isolated-failure convention
`GlobalMarketIntelligenceWorkflow` already uses one level up. An empty
universe (currently every penny/micro-cap category — see §7) simply
returns `()`, not an error.

`MarketDataNormalizer` (`app/global_markets/normalization/normalizer.py`)
maps one already-fetched `MarketQuote`/`HistoricalSeries` into
`NormalizedAssetSnapshot`. `market_cap`/`fully_diluted_valuation` are
always `None`: live-verified against `YahooFinanceProvider`,
`get_market_cap()` raises `ProviderConfigurationError` unconditionally
for every ticker (the chart endpoint has no market-cap data at all) — the
normalizer never calls it rather than making a guaranteed-useless
request. `avg_daily_traded_value` is derived from `average_volume *
price` when both are present.

No new `MarketDataProvider`-like abstraction was introduced for
Forex/Crypto: the existing ABC (`app/providers/market_data/provider.py`)
was live-verified against 5 real tickers per asset class (50 total,
`get_quote` + `get_price_history`) and works correctly across all five
main asset classes — equity-specific methods correctly raise
`ProviderConfigurationError` for non-equity tickers, which is already
the pre-existing, correct behavior this pipeline relies on.

## 6. Orchestration & idempotency

`GlobalMarketIntelligenceWorkflow` (`app/workflows/global_markets/pipeline.py`)
satisfies `WorkflowProtocol`. Per execution: resolve `run_date` as the
master scheduler's own `Asia/Kolkata` calendar date, then for each
configured category (independently, try/except-isolated) resolve its
`MarketSessionContext` and — when `category_pipeline`/`universe_registry`/
`ranked_asset_repository` are all wired — run `CategoryDataPipeline` and
persist its `RankedAsset`s via `replace_ranked_assets` (delete-then-insert
for that one `(run_id, category)`, never touching another category's or
run's rows). One category's failure (session resolution *or* data
pipeline) becomes only that category's own failed `CategoryRunOutcome` —
`IntelligenceRun.derive_status()` computes `COMPLETED`/`PARTIAL`/`FAILED`
purely from those outcomes, never set independently.

Idempotency: `execute()` checks `get_run_by_date(run_date)` *before*
doing any category resolution or data-fetch work, returning the existing
run immediately if one is already stored — a second scheduler fire (or a
manual retry) never redoes expensive work. `create_run`'s own
`UniqueConstraint("run_date")` is the last line of defense against a
genuine concurrent race; on that race, this run's own already-persisted
`RankedAsset` rows (if any) simply aren't referenced by the returned,
already-existing `IntelligenceRun` — an accepted tradeoff (the original
Phase 1 code already discarded a freshly-built `IntelligenceRun` object
on the same race), not full distributed-lock idempotency.

Any of `category_pipeline`/`universe_registry`/`ranked_asset_repository`
being `None` (e.g. no live `MarketDataProvider`, or PostgreSQL
unreachable at startup) degrades the workflow back to Phase 1's
session-resolution-only behavior — never crashes.

Phase 3: once a category's `RankedAsset`s are fetched and persisted, if
that batch is non-empty and `research_agent`/`penny_microcap_agent`/
`report_repository` are wired, `_generate_and_persist_report` builds the
right agent's request (`GlobalMarketsResearchRequest` for
`MAIN_REPORT_CATEGORIES`, `PennyMicrocapIntelligenceRequest` for
`PENNY_MICROCAP_REPORT_CATEGORIES`), calls that agent's `run()`, and
persists the result via `save_report`. This step is wrapped in its own
bare `except Exception: return` — a narrative failure (LLM timeout, a
malformed response, an ungrounded commentary) never flips the category's
own `succeeded` outcome, because the deterministic ranking step already
completed and persisted by the time this runs. A missing
`CategoryIntelligenceReport` for a given `(run_id, category)` is itself
the honest signal that no narrative exists for it — never masked as a
category failure, and never silently retried within the same execution.

## 7. Universes

`UniverseRegistry` (`app/global_markets/universe/registry.py`) maps each
`ReportCategory` to its candidate ticker set; `.get()` returning `()` is
a normal, honest state, never an error. `DEFAULT_UNIVERSES`
(`universe/defaults.py`) hardcodes a live-verified **15-ticker** universe
for each of the five main categories — enough to cover a full
`top_n == 15` selection. Every ticker was individually verified (real
daily history fetched via the actual `YahooFinanceProvider`) before being
added, per the "never fabricate financial facts" principle.

**Penny/micro-cap categories:**

- `INDIA_PENNY_STOCK` / `US_PENNY_STOCK` / `CHINA_PENNY_STOCK` carry a
  small **FALLBACK-ONLY** static universe (each entry live-verified as
  currently listed, actively trading, and — at verification time — under
  its market's `max_price` gate). These lists are deliberately short:
  only names that could be verified, never padded to reach `top_n`. The
  downstream eligibility gate re-checks price and every other criterion
  fresh each run.
- `LOW_CAP_CRYPTO` stays **deliberately empty** — its eligibility gate
  depends entirely on market-cap / daily-volume data the pipeline has no
  source for, so `ConfigurableEligibilityProvider` structurally rejects
  every candidate (`data_completeness_ratio` below the 0.5 minimum).
  Adding tickers would only produce names that can never pass.

As of Phase 6c, `GlobalMarketIntelligenceWorkflow._resolve_universe` can
populate the penny/micro-cap universes a different way: when a
`screening_provider` is configured (`GLOBAL_MARKET_SCREENING_ENABLED=true`),
each penny/micro-cap category's universe is freshly *live-discovered* on
every run instead — see §14. The static `DEFAULT_UNIVERSES` entry remains
**fallback only** — consulted solely when screening is unconfigured,
returns nothing, or fails; a successful discovery is never overridden by
it. The eligibility/scoring/risk-classification machinery
those categories need is fully built, tested, and (Phase 6b) wired with
real per-market `PennyStockEligibilityCriteria` (see §4); once screening
is enabled, `PennyMicrocapIntelligenceAgent` finally has real ranked
assets to interpret, not just prompt/parsing/grounding logic with nothing
to run against (see §11).

## 8. Persistence

Three independent tables under one `Base`
(`app/repositories/global_markets/postgres/models.py`), three separate
repository ABCs:

- `global_market_intelligence_runs` (`BaseGlobalMarketRunRepository`,
  Phase 1) — one row per run: id, run_date (unique), status,
  `category_outcomes` (JSON), triggered_by, started_at, completed_at.
- `global_market_ranked_assets` (`BaseRankedAssetRepository`, Phase 2) —
  one row per `(run_id, category, ticker)`: rank, final_score,
  `factor_scores` (JSON), `performance_windows` (JSON — the full ten
  `WindowedPerformance` entries, 24H..5Y, verbatim from the
  `AssetPerformanceProfile` the ranking consumed; `NOT NULL DEFAULT '[]'`,
  so a pre-0010 row reads back as `[]`), `snapshot` (JSON, the full
  `NormalizedAssetSnapshot`), `risk_classification`. Primary key is the
  deterministic `"{run_id}:{category}:{ticker}"` string (see
  `postgres/mapper.py::ranked_asset_id`) — the PK itself is the
  uniqueness constraint, and `replace_ranked_assets`'
  delete-then-insert-for-one-category semantics are collision-free by
  construction.
- `global_market_intelligence_reports` (`BaseIntelligenceReportRepository`,
  Phase 3) — one row per `(run_id, category)`: `generated_at`,
  `overall_summary`, `asset_commentaries` (JSON), `risk_note`, `provider`,
  `model`. Primary key is the deterministic `"{run_id}:{category}"`
  string (`postgres/mapper.py::intelligence_report_id`) — `save_report`'s
  own delete-then-insert upsert is collision-free the same way.

Migrations: `alembic/versions/0007_global_market_runs.py` (run tracking),
`0008_global_market_ranked_assets.py` (ranked assets), and
`0009_global_market_reports.py` (narrative reports) all drive DDL
directly off the real ORM `Base.metadata` — never hand-transcribed, can
never drift from the actual models. `0010_ranked_asset_performance_windows.py`
is the first incremental *ALTER* here — an inspector-guarded,
column-existence-checked `add_column`/`drop_column` for
`performance_windows`, following the `0003_risk_market_data_coverage`
idiom (safe on a fresh DB and on one stamped at an older revision). See
`docs/database/MIGRATIONS.md` for the revision-id-length constraint all
four respect (`0010`'s stored id is the shortened
`0010_ranked_asset_perf_windows`, 30 chars). All four are exercised by a
real Alembic upgrade/downgrade cycle in `tests/operations/`
(`test_ranked_asset_performance_windows_migration.py` for `0010`).

## 9. Scheduling

`GLOBAL_MARKETS_WORKFLOW_ID = "global_market_intelligence"`, registered
via `register_global_market_intelligence_schedule`
(`app/bootstrap.py`) with `ScheduleTriggerType.CRON` and an explicit
`Schedule.timezone="Asia/Kolkata"` — `APSchedulerService._build_trigger`
evaluates `"30 8 * * *"` in that timezone, never the container's own
local/system timezone. Gated by `AppSettings.global_markets_enabled`
(default `False`, like every other scheduled-job feature flag in this
codebase) — upgrading an existing deployment never silently starts this
schedule.

**Run-now trigger**: `scripts/run_global_market_intelligence.py` executes
one workflow run on demand (`scheduler.run_schedule(GLOBAL_MARKETS_WORKFLOW_ID)`),
printing a JSON summary — run id, status, and per-category
succeeded/error plus persisted ranked-asset count. Same operational
pattern as `scripts/run_market_data_refresh.py` / `run_ingestion.py`:
only reachable by whoever can already run a command inside the backend
container, and it still respects the `global_markets_enabled` gate (exits
with a `"disabled"` message when the flag is off) and the per-`run_date`
idempotency short-circuit (§6) — a second run for a date that already has
one returns the existing run, never re-fetches.

## 10. What's still missing (Phase 6d+)

- A market-cap-capable market-data source, so `NormalizedAssetSnapshot
  .market_cap`/`.bid_ask_spread_percent`/`.is_suspended`/`.is_delisted`
  stop being permanently `None`/`False` and the real
  `min_market_cap`/`max_market_cap`/`max_spread_percent`/
  `exclude_suspended`/`exclude_delisted` eligibility criteria (§4) can
  actually reject an asset, not just record reduced
  `data_completeness_ratio` — this affects both the eligibility gate and,
  more visibly, the screening/discovery step (§14): CoinGecko-discovered
  `LOW_CAP_CRYPTO` candidates in particular are frequently *not*
  quotable via `YahooFinanceProvider` at all (a real vendor-coverage gap,
  not a bug — see §14's own "Known limitation").
- `GLOBAL_MARKET_SCREENING_ENABLED` defaults to `false` — an operator
  must deliberately opt in (see `docs/release/PRODUCTION_CONFIGURATION_GUIDE.md`).
  Until then, the three equity penny categories rank over their small
  static fallback universe (§7), and `LOW_CAP_CRYPTO` produces nothing.
- **Main-category universes now hold 15 tickers each** (`DEFAULT_UNIVERSES`,
  §7), so those categories rank a full Top-15. Widening further, or wiring
  main-category screening, would only matter for a larger candidate pool.
- Yahoo's unofficial screener endpoint (§14) is prone to
  `429 Too Many Requests` on its crumb handshake under load; when it
  rate-limits, the three equity penny categories degrade to their empty
  static universe for that run (`global_market_intelligence_screening_failed`
  logged, category still `succeeded` with an empty result — §6). A later
  run typically succeeds.

## 11. LLM narrative interpretation (Phase 3)

Two agents, exactly as scoped — nothing else in this feature reasons or
generates prose:

- **`GlobalMarketsResearchAgent`** (AGT-006,
  `app/agents/global_markets_research/`) — the five `MAIN_REPORT_CATEGORIES`.
- **`PennyMicrocapIntelligenceAgent`** (AGT-007,
  `app/agents/penny_microcap_intelligence/`) — the four
  `PENNY_MICROCAP_REPORT_CATEGORIES`, with one extra business rule: its
  report's `risk_note` is REQUIRED (never `None`), unlike the main-category
  agent's report, since penny/micro-cap coverage inherently carries lower
  data confidence and higher volatility.

Both follow `CompanyResearchAgent`'s (AGT-004) own established shape
exactly: constructor eagerly verifies its `PromptTemplate` is registered
(fails fast, not at first `run()`), a four-tier typed exception hierarchy
(`PromptRenderingError`/`LLMGenerationError`/`ResponseParsingError`/
`ReportValidationError` — never a raw `LLMServiceError`/pydantic
exception escapes), and the same markdown-code-fence-tolerance regex
observed necessary against the real Claude API. Neither agent computes
anything: `input_schema` is a `RankedAsset` tuple plus a
`MarketSessionContext` (already fetched, ranked, and persisted one level
up by `CategoryDataPipeline`/`GlobalMarketIntelligenceWorkflow`);
`output_schema` is `CategoryIntelligenceReport`
(`app/global_markets/intelligence_report.py`).

**Grounding, structurally enforced, not just prompted**: every system
prompt instructs the model to reason only over the supplied ranked-asset
data and never re-rank/re-score/invent a fact — the same discipline
`CompanyResearchAgent` already applies to retrieved evidence. On top of
that, `validate_commentaries_are_grounded` (`intelligence_report.py`)
checks, after parsing, that every `asset_commentaries` entry's
`(ticker, rank)` pair exactly matches one of the `RankedAsset`s the model
was actually given; a hallucinated reference raises `ReportValidationError`
rather than being silently accepted into a persisted report.

**Terminology discipline**: `PennyMicrocapIntelligenceAgent`'s system
prompt explicitly instructs the model that a `RiskClassification` (e.g.
`EXTREME_MOMENTUM_EXTREME_RISK`) is a data-driven momentum/volatility
signal only — never proof of fraud or manipulation — extending to the
LLM's own prose the same terminology-careful framing
`app.global_markets.ranking.classification` already applies
deterministically to the classification itself (see §4).

Prompt templates are registered once, at startup, in
`app.bootstrap.build_prompt_registry()` alongside every other agent's
templates — never auto-discovered (`PromptRegistry`'s own contract).
Both agents are `None`-safe at construction time in bootstrap
(`build_global_markets_research_agent`/`build_penny_microcap_intelligence_agent`
return `None` when `LLMService` is unavailable), and the workflow itself
never calls an agent that's `None` (see §6's own description of
`_generate_and_persist_report`).

## 12. Read-only API surface (Phase 4)

`app/api/v1/global_markets/` (`router.py` + `dependencies.py`), mounted
at `/api/v1/global-markets` via `app/api/v1/router.py`. Read-only by
design: every entity exposed (`IntelligenceRun`/`RankedAsset`/
`CategoryIntelligenceReport`) is produced only by the scheduled
`GlobalMarketIntelligenceWorkflow` — there is no POST/trigger endpoint,
and none is planned; manually invoking the pipeline over HTTP would mean
triggering real LLM calls on demand, a cost/operational surface
deliberately left to the scheduler alone.

Eight endpoints, all requiring the single `global_markets:read`
permission (`Depends(require_policy(RequirePermission("global_markets:read")))`,
the same `require_policy` every other authenticated `/api/v1` router
uses — domain data here follows the authenticated convention, unlike the
public System/Health group):

```
GET /global-markets/categories                                          -> SuccessResponse[tuple[ReportCategoryDefinition, ...]]
GET /global-markets/runs                                                -> PaginatedResponse[IntelligenceRun]
GET /global-markets/runs/latest                                         -> SuccessResponse[IntelligenceRun]
GET /global-markets/runs/{run_id}                                       -> SuccessResponse[IntelligenceRun]
GET /global-markets/runs/{run_id}/ranked-assets                         -> PaginatedResponse[RankedAsset]
GET /global-markets/runs/{run_id}/reports                               -> PaginatedResponse[CategoryIntelligenceReport]
GET /global-markets/runs/{run_id}/categories/{category}/ranked-assets   -> PaginatedResponse[RankedAsset]
GET /global-markets/runs/{run_id}/categories/{category}/report          -> SuccessResponse[CategoryIntelligenceReport]
```

`/runs/latest` is registered before `/runs/{run_id}` — same
registration-order requirement `app/api/v1/portfolio/router.py`'s own
docstring documents (a literal path segment must precede a variable one
at the same depth, or the variable route swallows it).

Each `RankedAsset` in a `ranked-assets` response carries its full
`performance_windows` array (ten `WindowedPerformance` entries, 24H..5Y —
§3/§8); no new endpoint or query parameter was added for it, it rides the
existing `RankedAsset` shape.

**Domain models returned directly**, no HTTP-layer DTOs — `IntelligenceRun`/
`RankedAsset`/`CategoryIntelligenceReport` are already persisted with
natural identity (`id` / `run_id`+`category`+`ticker` / `run_id`+`category`),
matching the convention `app/api/v1/watchlists`/`portfolio`/`screening`
already establish (return the same model the service/repository itself
uses, wrapped only in the shared `SuccessResponse[T]`/`PaginatedResponse[T]`
envelope — `app/api/v1/schemas/common.py`). Pagination
(`app/api/v1/schemas/pagination.py`) is applied in-memory over whatever
list the repository already returned, exactly like every other
paginated `/api/v1` endpoint — no query pushed down into the repository.

**404 vs 503**, deliberately different from most other `/api/v1`
routers: every global-markets repository's own `get_*`/`list_*` method
returns `None`/`[]` for a missing record rather than raising a domain
`*NotFoundError` (see each repository's own docstring), so this router
cannot rely on the centralized, naming-convention-based
`handle_domain_error`. A missing `run_id`/report is instead translated
with a direct `raise HTTPException(404, ...)` in the handler itself —
the same already-established pattern `app.api.v1.auth.router` uses for
a status code the shared handler doesn't infer. A repository that is
`None` on `app.state` (e.g. PostgreSQL never initialized) is still
handled entirely by the existing `resolve_app_state` helper
(`app/api/dependencies/state.py`) — 503, before the handler body ever
runs; no route-specific code needed for that case.

No changes to `app/bootstrap.py` were required for this phase — the
three repositories this router depends on (`global_market_run_repository`/
`global_market_ranked_asset_repository`/`global_market_report_repository`)
were already constructed and placed on `app.state` in Phase 2/3.

## 13. WebSocket distribution (Phase 5)

Publishes one new event through the **existing** `/ws` real-time
framework (`app/api/ws/`, Sprint 59) — no second WebSocket system, no new
connection registry, no new auth path. Every piece below is an addition
to the existing five framework modules plus the workflow itself; nothing
in `app/api/ws/router.py`, `connection_manager/`, or `subscriptions/`
changed.

**Event**: `GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED`
(`app/api/ws/event_models/event_type.py`). Schema:
`GlobalMarketIntelligenceRunEvent(BaseEvent[IntelligenceRun])`
(`event_models/events.py`) — the payload is the exact same
`IntelligenceRun` `GlobalMarketIntelligenceWorkflow.execute()` already
returns, never reshaped or duplicated. This single event type covers all
three terminal outcomes honestly: the payload's own `status`
(`COMPLETED`/`PARTIAL`/`FAILED`) is what a subscriber reads to tell them
apart — a `FAILED` run is never announced as if it were a success.
`correlation_id` is `IntelligenceRun.id`. `IntelligenceRun` already
carries everything a subscriber needs to know a report is ready without
fetching it blind: `id`/`run_date` (what to fetch), `status` (complete/
degraded/failed), and `category_outcomes` (which categories succeeded,
each with its own `market_session_context.data_freshness_status`) — the
`RankedAsset`/`CategoryIntelligenceReport` payloads themselves are
deliberately **not** embedded; a subscriber fetches those separately via
`/api/v1/global-markets/runs/{run_id}/...` (§12) once notified.

**Publisher method**: `EventPublisher.publish_global_market_intelligence_run_completed(run: IntelligenceRun) -> int`
(`app/api/ws/publishers/event_publisher.py`) — the same
already-computed-result-in, `ConnectionManager.broadcast()`-out shape
every other publisher method uses.

**Permission**: subscribing requires `global_markets:read`
(`app/api/ws/dependencies/permissions.py`) — the exact same string the
REST router (§12) already requires, evaluated by the same
`PolicyEvaluator`/`RequirePermission` REST uses, at subscribe time (not
per delivered message — see `WEBSOCKET_FRAMEWORK.md` §3/§4 for how
subscription-time authorization and topic-based delivery are two
independent axes in this framework).

**Trigger point & idempotency**: `GlobalMarketIntelligenceWorkflow.execute()`
(`app/workflows/global_markets/pipeline.py`) publishes exactly once,
immediately after `create_run` durably persists the run — never before
persistence (a client fetching the run over REST the instant the event
arrives always finds it there), and never on either idempotent
short-circuit path:

```
execute()
  |
  +--> get_run_by_date(run_date) already exists? -> return it, NO publish (already announced the first time)
  |
  +--> resolve every category, build `run`
  |
  +--> create_run(run) succeeds -> _publish_run_completed(persisted_run) -> return persisted_run
  |
  +--> create_run(run) raises DuplicateIntelligenceRunError (a genuine race)
         -> return the winning execution's own run, NO publish (that execution already published)
```

`event_publisher: EventPublisher | None = None` is an optional
constructor parameter on `GlobalMarketIntelligenceWorkflow` — `None` (the
default) publishes nothing, preserving every Phase 1–4 test and caller
unchanged, the same "degrade, never crash" shape
`MarketDataRefreshWorkflow`'s own `event_publisher` parameter already
established (`docs/architecture/WEBSOCKET_FRAMEWORK.md` §8).

**Reliability**: a delivery failure is caught inside a dedicated
`_publish_run_completed` helper and logged
(`global_market_intelligence_publish_failed`), never allowed to fail an
already-persisted run — mirroring `ContinuousIntelligenceService`'s own
established "a publish failure must not lose the underlying detected
state" precedent (`app/services/continuous_intelligence/service.py`).
Zero connected/subscribed clients is not a failure either:
`ConnectionManager.broadcast()` returns `0` delivered, and the workflow
returns its persisted run normally either way. A dead socket encountered
mid-broadcast is disconnected and skipped by `ConnectionManager` itself
(existing framework behavior, untouched).

**Bootstrap wiring**: `build_global_market_intelligence_workflow` gained
one new optional `event_publisher: EventPublisher | None = None`
parameter, threaded through from `getattr(app.state, "event_publisher",
None)` at the call site — the exact pattern
`build_market_data_refresh_workflow`/`build_continuous_intelligence_service`
already use for this same shared, `app/main.py`-constructed publisher.

## 14. Penny/micro-cap candidate discovery (Phase 6c)

`app/global_markets/screening/` — the "which real tickers exist in this
market within this price/market-cap band" capability neither
`MarketDataProvider` (per-ticker lookups only) nor `app/screening`
(evaluates an already-supplied list, no market-wide discovery) provides.
Gated by `GLOBAL_MARKET_SCREENING_ENABLED` (default `false` — see
`docs/release/PRODUCTION_CONFIGURATION_GUIDE.md`); `None` behaves
exactly like pre-Phase-6c, falling straight through to
`UniverseRegistry`'s static (empty) entry.

**Contract**: `PennyStockScreeningProvider.discover(category, criteria, limit) -> tuple[UniverseEntry, ...]`
(`screening/provider.py`) only ever *proposes* identities — every
candidate still goes through the exact same
`MarketDataProvider.get_quote()` -> `ConfigurableEligibilityProvider`
pipeline any other `UniverseEntry` does (`CategoryDataPipeline.run`, §5);
`criteria` (the same `PennyStockEligibilityCriteria` from §4, via
`criteria_for_category`) only narrows the *vendor query itself*, never
substitutes for the real downstream eligibility check.

**Two real vendors, no API key for either** (`CompositePennyStockScreeningProvider`
routes by category):

- **`YahooScreenerProvider`** — India/US/China equity penny categories,
  via Yahoo Finance's unofficial, undocumented screener endpoint
  (`POST /v1/finance/screener`), live-verified during implementation.
  Reuses the same vendor `YahooFinanceProvider` already depends on for
  quotes/history (no new vendor trust boundary), though the screener
  endpoint specifically needs a session cookie + CSRF "crumb"
  (`GET /v1/test/getcrumb`, cached, refreshed once on a 401). The
  `quoteType=EQUITY` query filter does not reliably exclude mutual
  funds/ETFs (observed live) — `_NON_COMMON_EQUITY_NAME_SUBSTRINGS` is a
  documented, best-effort name heuristic, not a guarantee.
- **`CoinGeckoScreeningProvider`** — `LOW_CAP_CRYPTO` only, via
  CoinGecko's public, no-key `/coins/markets` endpoint, live-verified.
  Never gates on unit token price (the same rule §4's `LOW_CAP_CRYPTO`
  criteria already enforces) — filters by `market_cap` alone, scanning
  `order=market_cap_desc` and stopping once a page falls below
  `criteria.min_market_cap` (bounded to `max_pages` regardless). A `0`/
  `null` market cap (observed live for inactive listings) is excluded
  outright, never treated as "eligible because it's small." A documented
  stablecoin-symbol denylist excludes fiat-pegged coins that would
  otherwise trivially satisfy a market-cap band while being uninteresting
  as a "discovery" candidate.

**Trigger point & degrade rule**: `GlobalMarketIntelligenceWorkflow._resolve_universe`
(`app/workflows/global_markets/pipeline.py`), called from
`_resolve_category` in place of a direct `UniverseRegistry.get()` call:

```
_resolve_universe(category, is_penny_microcap)
  |
  +--> not penny/micro-cap, or no screening_provider configured -> UniverseRegistry.get(category)  [unchanged pre-Phase-6c behavior]
  |
  +--> screening_provider.discover(category, criteria, limit) raises -> log, degrade to UniverseRegistry.get(category)
  |
  +--> discover() returns () -> degrade to UniverseRegistry.get(category)
  |
  +--> discover() returns 1+ entries -> use them, UniverseRegistry never consulted
```

A screening failure never fails the category's own `succeeded` outcome —
the same "an optional dependency's failure degrades, never crashes"
convention every other Phase 2/3/5 integration point in this workflow
already establishes (narrative generation, event publishing).

`limit` passed to `discover()` is `min(top_n * 3, 100)`, not `top_n`
itself — headroom against later attrition: a discovered candidate that
fails the real per-ticker `MarketDataProvider.get_quote()` fetch in
`CategoryDataPipeline.run` (§5) is silently excluded, exactly like any
other universe entry today. This headroom is most load-bearing for
`LOW_CAP_CRYPTO`: **known limitation** — CoinGecko tracks far more coins
than Yahoo Finance's chart endpoint actually has data for, so a
discovered low-cap token Yahoo cannot quote simply disappears at the
per-ticker fetch stage. Honest and expected, not a bug — mitigated, not
eliminated, by the overfetch.

## 15. Frontend trailing-return display (Phase 6a extension)

`frontend/src/features/global-markets/` renders the latest daily run per
segment (from `/runs/latest` + the `GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED`
WebSocket event — §13). `RankedAssetTable` shows each asset's **1Y / 3Y /
5Y** trailing returns as their own columns (signed, coloured green/red by
sign); the expandable per-row detail panel shows the full ten-window
breakdown (24H..5Y) alongside the factor-score bars and any per-asset
LLM commentary. A window with `is_complete=false` is rendered muted with
a `*` and an explanatory footnote — never shown as a full-window return,
the same discipline `WindowedPerformance` enforces server-side (§3).
`types/global-markets.ts` mirrors `PerformanceWindow` /
`WindowedPerformance` / `RankedAsset.performance_windows` verbatim.

## 16. Daily-intelligence surfacing (Phase 8)

Phase 8 makes the daily run visible from where users actually start,
without adding any new backend surface — every piece below is a pure
projection of the already-persisted run:

- **"Today's Global Markets" dashboard card**
  (`features/dashboard/todays-global-markets-card.tsx`, registered in
  `dashboard-card-registry.tsx` with `requiresPermission:
  "global_markets:read"`). Shows the latest run's date, status, IST
  completion time (`formatRunTimestampIst` — the workflow is IST-native,
  scheduled 08:30 Asia/Kolkata), and a top-3 ticker preview per segment.
  Handles loading / empty (no run yet) / stale (run date ≥ 2 days old) /
  error states. "View full report →" links to `/global-markets`. The
  dashboard layout store gained a `merge` so a returning user (persisted
  `cardOrder` in `localStorage`) still sees the newly-registered card.
- **"Top Picks" tab** (`features/global-markets/top-picks-panel.tsx`,
  first tab on `/global-markets`, the store's default `activeTab`).
  Aggregates rank 1–3 across all nine categories via
  `useTopPicksAcrossCategories` — one cached query per category (the
  all-categories endpoint is capped below 9×20 rows), sliced and grouped
  in the browser, never re-ranked. Shows the run-level "as of
  {completed_at} IST" timestamp (also added to the page header).
- **Permissions.** `global_markets:read` is granted through a dedicated
  additive role, `GLOBAL_MARKETS_READ` (id `role-global-markets-read`),
  assigned by `scripts/grant_global_markets_access.py` — no existing role
  is mutated and authorization is never weakened. See
  `docs/release/ADMINISTRATOR_GUIDE.md`.
