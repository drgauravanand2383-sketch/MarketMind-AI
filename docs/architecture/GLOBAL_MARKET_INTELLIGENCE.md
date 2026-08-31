# Global Market Intelligence

**Phase 1 (foundation) + Phase 2 (deterministic pipeline) + Phase 3
(narrative interpretation) + Phase 4 (read-only API surface) are committed
and pushed to `main`. Phase 5 (WebSocket distribution only — see §13) is
implemented but uncommitted, pending review.** Daily, multi-market
intelligence covering nine reporting categories across five market regions
(India, US, China, Forex, Crypto), published once daily via a scheduled
workflow, readable over `/api/v1/global-markets`, and now announced in
real time over the existing `/ws` framework. Frontend consumption of
either surface, and real per-market penny-stock eligibility/screening
data, remain deliberately deferred — see §10.

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
computes six `PerformanceWindow`s (10D/15D/1M/3M/6M/1Y) per asset from an
already-fetched `HistoricalSeries` — no I/O. Methodology is explicit per
market region, never one blanket calendar-day subtraction:

- **10D/15D, session-based markets** (equities, forex): the Nth most
  recent *bar*, not calendar-day subtraction — correct by construction
  because a real provider's daily series only contains bars for days that
  actually traded.
- **10D/15D, crypto**: calendar-day anchored (crypto trades every day).
- **1M/3M/6M/1Y, every region**: calendar month/year subtraction anchored
  on the latest bar's date (stdlib `calendar.monthrange`), snapped to the
  nearest bar at-or-before the anchor.

A window that the asset's history doesn't fully cover is still reported,
with `WindowedPerformance.is_complete=False` — never silently dropped or
presented as a full-window return.

## 4. Ranking & eligibility (Phase 1 contract, Phase 2 real scoring)

`RankingFactor` (`app/global_markets/ranking/models.py`) names twelve
possible inputs; `FactorScoringService`
(`app/global_markets/ranking/factor_scoring.py`) currently computes five
of them — `PRICE_PERFORMANCE`, `MOMENTUM`, `VOLUME_LIQUIDITY`, `RISK`
(inverted: higher = safer), `SOURCE_CONFIDENCE` — all **cross-sectionally
min-max scaled to [0, 100] relative to the other assets in the same
batch**, never against a fixed absolute threshold (no universal "good
momentum" scale spans India equities, forex pairs, and crypto).
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
`data_completeness_ratio`, never counted as a pass or fail). No default
criteria are configured yet (Phase 4+, once real per-market thresholds
and a screening data source exist) — `CategoryDataPipeline` accepts an
optional `eligibility_provider` and simply skips filtering when `None`.

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
        +--> MarketDataProvider.get_quote() / get_price_history()   per ticker, isolated
        +--> MarketDataNormalizer.normalize()   -> NormalizedAssetSnapshot
        +--> [optional] PennyStockEligibilityProvider.evaluate()   -> drop ineligible
        +--> PerformanceCalculationService.calculate()   -> AssetPerformanceProfile
        +--> FactorScoringService.score_batch()   -> FactorScore per asset
        +--> WeightedRankingEngine.rank()   -> RankedAssetScore, truncated to top_n
        +--> [optional] classify()   -> RiskClassification (penny/micro-cap only)
        -> tuple[RankedAsset, ...]
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
(`universe/defaults.py`) hardcodes a live-verified 10-ticker universe for
each of the five main categories. **The four penny/micro-cap categories
are deliberately left empty** — fabricating specific penny-stock tickers
from training-data recall would violate this codebase's "never fabricate
financial facts" principle (training-data-recalled small-caps are
disproportionately likely to be delisted, stale, or wrong). The
eligibility/scoring/risk-classification machinery those categories need
is fully built and tested; only a real screening-data source and
per-market `PennyStockEligibilityCriteria` are missing (Phase 4+) — which
is also why `PennyMicrocapIntelligenceAgent` has real prompt/parsing/
grounding logic but nothing to actually interpret yet in this codebase's
current state (see §11).

## 8. Persistence

Three independent tables under one `Base`
(`app/repositories/global_markets/postgres/models.py`), three separate
repository ABCs:

- `global_market_intelligence_runs` (`BaseGlobalMarketRunRepository`,
  Phase 1) — one row per run: id, run_date (unique), status,
  `category_outcomes` (JSON), triggered_by, started_at, completed_at.
- `global_market_ranked_assets` (`BaseRankedAssetRepository`, Phase 2) —
  one row per `(run_id, category, ticker)`: rank, final_score,
  `factor_scores` (JSON), `snapshot` (JSON, the full `NormalizedAssetSnapshot`),
  `risk_classification`. Primary key is the deterministic
  `"{run_id}:{category}:{ticker}"` string (see
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
never drift from the actual models. See `docs/database/MIGRATIONS.md`
for the revision-id-length constraint all three respect.

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

## 10. What's still missing (Phase 6+)

- Frontend (India/US/China/Forex/Crypto tabs + Penny & Micro-Cap with 4
  sub-tabs) — including a WebSocket client consuming
  `GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED` (§13); `frontend/src/types/
  websocket.ts`'s `EventType`/`DomainEvent` unions do not yet have a
  matching arm.
- Real per-market `PennyStockEligibilityCriteria` and a penny/micro-cap
  screening data source (unblocks non-empty penny/micro-cap universes,
  and therefore real `PennyMicrocapIntelligenceAgent` output).

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
