# Portfolio Intelligence & Decision Integration

**Milestone 14 — post-v1.0.0 / v1.1 candidate.** Integrates News, Entity
Resolution (Milestone 12), Live Market Data (Milestone 13), Portfolio,
Risk, Strategy, Recommendations, Signals, and Alerts into one
market-aware Decision Center. v1.0.0's own scope, status, and sign-off
are unchanged by this document. See `docs/release/UPGRADE_POLICY.md`'s
versioning rules for what a v1.1 candidate capability means in this
repository.

**No second portfolio architecture was created.** Every existing service
(`WatchlistService`, `RiskAnalyticsService`, `StrategyEvaluationService`,
`PortfolioRecommendationService`, `SignalDetectionService`, `AlertService`,
`PortfolioIntelligenceAgent`) is reused exactly as it already existed;
this milestone only adds new composition and additive fields on top.

**Milestone 15 update**: `PortfolioMarketSnapshotService`/`signal_adapter`
(this document's own §2/§5) are now also reused by `ContinuousIntelligenceService`
to detect and proactively notify on market/news/decision changes, on a
schedule — see `docs/architecture/CONTINUOUS_INTELLIGENCE.md` for the full
design. Nothing documented below changed; Milestone 15 only adds a new
consumer of these same services.

## 1. Architecture — what actually connects, and what doesn't

Before writing any integration code, this milestone inspected the real
relationships between `PortfolioExposure`, `RecommendationResult`,
`RiskAssessment`, `StrategyEvaluationResult`, `SignalResult`, and
`AlertEvaluationResult` (per its own §1 instruction). The confirmed,
one-way evaluation chain:

```
CandidateEvidence
      |
      v  PortfolioRecommendationService.score_candidate()
RecommendationCandidate  ---(supporting_signals)--->  SignalResult
      |                                                    ^
      v  RecommendationResult                              |
      |                                              SignalDetectionService
      +--> StrategyEvaluationService.evaluate_recommendations()   .evaluate_company()
      |         -> StrategyEvaluationResult                       ^
      |                                                            |
      +--> RiskAnalyticsService.assess_portfolio()          MarketDataSnapshot.quote
                -> RiskAssessment                                  ^
                                                                    |
                                                    signal_adapter.build_market_data_snapshot()
                                                                    ^
                                                                    |
                                              PortfolioMarketSnapshotService (NEW, composition only)
                                                 --uses-->  MarketSnapshotService (Milestone 13)
                                                 --uses-->  EntityResolutionService (Milestone 12)
```

**Risk and Strategy are strictly downstream of Recommendations and cannot
feed back into it** — confirmed by reading `app.risk.engine`/
`app.strategy.engine` directly, not assumed. This matters: §7 of this
milestone's own spec asks every recommendation to identify whether market
data contributed "directly / indirectly through risk / not at all," but
"indirectly through risk" does not describe a real pathway in this
codebase's architecture. The literal, honest equivalent —
**"indirectly through signals"** — is what `MarketContribution` actually
reports; see §7 below and `app.recommendations.models.MarketContribution`'s
own docstring for the full reasoning, flagged there as a documented
interpretation rather than a silent deviation.

`AlertService` never consumes market data directly — only `SignalResult`
— so Alerts become market-aware **purely indirectly and automatically**
the moment Signals are evaluated against real market data (§9). No
`app.alerts` file was changed.

## 2. Portfolio Market Snapshot (NEW)

`app.services.portfolio_market_snapshot.PortfolioMarketSnapshotService` —
pure composition of two existing Milestone 12/13 services, no new
provider call, no new cache:

```python
PortfolioMarketSnapshotService(market_snapshot_service, entity_resolver)
    .get_portfolio_snapshot(watchlist) -> PortfolioMarketSnapshot
```

For each `WatchlistItem`, resolves via
`EntityResolutionService.lookup_by_name_or_ticker()`, batches unique
resolved entities through `MarketSnapshotService.get_snapshots()`
(reusing Milestone 13's own partial-failure-safe batching — one bad
ticker never affects another), and maps results back per item. An
unresolved item is synthesized as `MarketSnapshotResult(status=
ENTITY_NOT_MAPPED)` — never a guess.

`portfolio_id` is the watchlist's own `id` — see §15 below.

### Valuation is always `VALUATION_UNAVAILABLE`

`WatchlistItem` (`app.watchlist.models`) carries `ticker`, `company_name`,
`country`, `sector`, `theme`, `source_agent`, `confidence`, `reason`,
`added_at`, `notes` — **no quantity, position size, market value, or
weight field exists anywhere in this codebase.** Per §3's own explicit
instruction ("only calculate if the repository has quantity/position
size/market value/weights; otherwise produce an explicit typed state"),
`PortfolioMarketSnapshot.valuation_status` is always the single-member
`ValuationStatus.VALUATION_UNAVAILABLE` enum, with a human-readable
`valuation_unavailable_reason`. P&L, return, gains, and benchmark
comparison follow the identical rule and are not computed anywhere — none
of them are representable without the same missing quantity/cost-basis
data.

## 3. Recommendations — additive market fields

`CandidateEvidence` gained one new optional field:
`market_snapshot: MarketSnapshotResult | None = None` — supplied by the
caller (this engine still never fetches market data itself, unchanged
from Milestone 13's own boundary). `RecommendationCandidate` gained five
new fields, all additive, all defaulting to a value that reproduces the
exact pre-Milestone-14 shape when omitted:

| Field | Type | Populated when |
|---|---|---|
| `market_price` | `float \| None` | `market_snapshot.status` is `FRESH`/`STALE` |
| `market_change_percent` | `float \| None` | same |
| `market_freshness` | `MarketSnapshotStatus \| None` | `market_snapshot` was supplied at all |
| `market_snapshot` | `MarketSnapshotResult \| None` | passthrough of the supplied evidence |
| `market_contribution` | `"direct" \| "indirect" \| "none"` | always computed — see below |

`market_price`/`market_change_percent` are **never fabricated**: an
`ENTITY_NOT_MAPPED` or provider-failure status leaves both `None` even
though `market_freshness` still honestly records the failure reason.

**`market_contribution`** (§7's own "no hidden weighting... all scoring
contributions must remain inspectable" requirement, satisfied literally):

- `"direct"` — a `FRESH`/`STALE` market snapshot was supplied for this
  candidate.
- `"indirect"` — no direct snapshot, but at least one triggered
  `supporting_signals` entry was evaluated against a `"quote.*"`-namespaced
  condition (Signal Detection is the one real pathway market data can
  reach a candidate through, other than directly — see §1's flagged
  interpretation).
- `"none"` — neither applies; this candidate's score is byte-identical to
  what it would have been before Milestone 14.

The actual scoring formula (`_derive_components`/`_weighted_score`) is
**completely unchanged** — market fields are pure passthrough/annotation,
never a scoring input. Verified by a dedicated regression test asserting
`overall_score`/`confidence` are identical with and without a supplied
market snapshot (`tests/recommendations/test_market_integration.py
::test_scoring_formula_unaffected_by_market_snapshot_presence`).

## 4. Strategy — zero engine changes

`app.strategy.models.StrategyRule.field` is derived generically from
`RecommendationCandidate.model_fields`
(`getattr(candidate, rule.field)`), excluding tuple-typed fields. This
meant Milestone 14's four new **scalar** fields (`market_price`,
`market_change_percent`, `market_freshness`, `market_contribution`)
became usable in Strategy rules **automatically, with zero engine code
changes** — a strategy can already write a rule like
`{"field": "market_change_percent", "operator": "GREATER_THAN", "value": 5}`.
The one nested field, `market_snapshot`, was added to
`_STRATEGY_RULE_FIELDS`'s existing exclusion set (it is not comparable by
a single operator/value pair, exactly like `supporting_signals`/
`supporting_alerts` already weren't).

## 5. Signals — an adapter, not a new capability

`app.signals.models.MarketDataSnapshot.quote: MarketQuote | None` already
existed (Sprint 46/47) — a near-exact structural match for Milestone 13's
own `MarketSnapshot`. Milestone 14 adds exactly one new module,
`app.services.portfolio_market_snapshot.signal_adapter`, with two pure
functions:

```python
market_snapshot_to_quote(result: MarketSnapshotResult | None) -> MarketQuote | None
build_market_data_snapshot(ticker, company_name, market_snapshot) -> MarketDataSnapshot
```

**FRESH-only, deliberately.** `MarketDataSnapshot` carries no freshness
field of its own — a condition evaluated against a populated `.quote` is
implicitly treated as evaluated against *current* data. Converting a
`STALE` (or worse) `MarketSnapshotResult` would silently promote stale
data to fresh inside Signal Detection, which §12 explicitly forbids.
Anything other than `FRESH` yields `quote=None`, which
`SignalDetectionService._evaluate_condition` (unmodified) already treats
as "missing data" and fails the condition — never a fabricated zero, the
same convention this engine already used for every other missing field.

Zero changes to `app.signals.engine`/`app.signals.models` — this is pure
composition.

## 6. Risk — an additive coverage field, formulas untouched

`app.risk.engine`'s own module docstring is explicit: this engine never
fetches market data, and `MARKET_CAP`/`VOLATILITY`/`LIQUIDITY` remain
exactly the same documented proxies they were before Milestone 14 (see
`docs/architecture/MARKET_DATA_ARCHITECTURE.md` §11 — this was a
deliberate Milestone 13 deferral, honored, not overridden, by this
milestone). §5's own instruction — "distinguish fresh from stale;
propagate unavailable honestly; no risk score from fabricated values;
existing calculations remain deterministic" — is satisfied by one new,
purely informational field:

```python
RiskAssessment.market_data_coverage: MarketDataCoverage  # new, additive
```

```python
class MarketDataCoverageStatus(str, Enum):
    NOT_EVALUATED  # no candidate carried market_freshness at all
    NONE           # evaluated, but no candidate came back FRESH/STALE
    PARTIAL        # some candidates FRESH/STALE, some not
    FULL           # every candidate FRESH/STALE
```

Computed from `RecommendationCandidate.market_freshness` across
`recommendation_result.recommendations` — `overall_risk_score`/
`risk_metrics` are provably unaffected (a dedicated regression test
constructs the same candidates with and without market data and asserts
byte-identical output:
`tests/risk/test_market_data_coverage.py
::test_market_data_coverage_never_changes_overall_risk_score`).

**Persistence**: `market_data_coverage` required one genuine schema
change — a new nullable `market_data_coverage` JSON column on the
existing `risk_assessments` table (Alembic migration
`0003_risk_market_data_coverage`, not a new table; see §11 below).

**`RISK_ASSESSMENT_COMPLETED` still has no REST trigger** — this is a
pre-existing, deliberate v1.0.0/Sprint 60 boundary (see
`docs/release/KNOWN_LIMITATIONS.md`), not something this milestone was
asked to fix (§26 forbids adding endpoints outside the frozen `/api/v1`
surface without genuine additive need). Risk still benefits from market
data automatically whenever `assess_portfolio()` *is* invoked against
market-aware candidates.

## 7. Recommendations transparency, Decision Context, and API surface

`GET /portfolio/intelligence` (the existing handler,
`app.api.v1.portfolio.router.get_portfolio_intelligence`) is the natural,
pre-existing composition point for a "Decision Context" — no second
business engine was built. The handler now, additively:

1. Runs `PortfolioIntelligenceAgent.run()` exactly as before (the agent's
   own dependencies, prompt, and narrative logic are **completely
   untouched** — it still never fetches market data itself).
2. Calls `PortfolioMarketSnapshotService.get_portfolio_snapshot(watchlist)`
   and attaches the result via `report.model_copy(update={"market_snapshot":
   ...})`.
3. Publishes `PORTFOLIO_INTELLIGENCE_UPDATED` (§9 below).

`PortfolioIntelligenceReport.market_snapshot: PortfolioMarketSnapshot |
None = None` — `None` on any report built without that extra step (e.g.
calling `agent.run()` directly, as the existing unit tests still do).

## 8. Failure isolation (§13)

Every integration point above inherits Milestone 13's own
never-raises-for-an-ordinary-failure guarantee:

- **Market provider unavailable** — `MarketSnapshotService.get_snapshots()`
  already converts any unexpected exception to `UNAVAILABLE`; nothing new
  was added here, because nothing needed to be.
- **One ticker unresolved** — `PortfolioMarketSnapshotService` maps each
  `WatchlistItem` independently; an unresolved one becomes
  `ENTITY_NOT_MAPPED` without touching any other item's result
  (`tests/services/portfolio_market_snapshot/test_service.py
  ::test_unmapped_entity_does_not_affect_other_items`).
- **One recommendation candidate's market fields** — `score_candidate()`
  is still called once per candidate; a missing/failed snapshot for one
  ticker cannot affect another candidate's fields.
- **Alert evaluation** — untouched, still per-signal, still cannot fail
  as a batch (Sprint 48's own existing guarantee).

## 9. Real-time events

Two new, additive `EventType` members, following the existing
`EventPublisher`/`ConnectionManager` framework (Sprint 59) exactly — no
new event bus, no polling loop:

| Event | Trigger point | Why this point |
|---|---|---|
| `MARKET_SNAPSHOT_REFRESHED` | `MarketDataRefreshWorkflow.execute()` (Milestone 13's own scheduled workflow) | Runs in-process inside the live server's own APScheduler execution — the *only* kind of trigger that shares real `ConnectionManager` state with actually-connected clients. An operational script builds its own throwaway `FastAPI()` app (see `scripts/run_market_data_refresh.py`) and shares no such state — publishing from one would be invisible to real users. |
| `PORTFOLIO_INTELLIGENCE_UPDATED` | `GET /portfolio/intelligence` | A real REST handler, same reasoning. |

Both are optional at construction time
(`MarketDataRefreshWorkflow(..., event_publisher=None)` reproduces
pre-Milestone-14 behavior exactly) — `EventPublisher` itself is
API-layer infrastructure, constructed in `app.main.create_app()`, and is
threaded into the composition root only as a `TYPE_CHECKING`-only import
plus a runtime `getattr(app.state, "event_publisher", None)` lookup, to
keep `app.bootstrap`'s existing "no `app.api` imports" boundary intact.

No existing event type was repurposed, and no new event bus/queue was
introduced.

**Subscription authorization** (`app.api.ws.dependencies.permissions
._EVENT_TYPE_PERMISSIONS`): `PORTFOLIO_INTELLIGENCE_UPDATED` requires
`portfolio:read` — matching its own REST source and its sibling events
(`RECOMMENDATION_GENERATED`/`RISK_ASSESSMENT_COMPLETED`). Caught and
fixed during this milestone's own live Docker acceptance (§19): a new
`EventType` left out of that mapping resolves to "no permission
required," the same posture `HEALTH_STATUS_CHANGED` deliberately uses —
correct for that one event, but not for a portfolio-scoped one.
`MARKET_SNAPSHOT_REFRESHED` is left unmapped deliberately: it has no
per-portfolio scope and no REST source to inherit a permission from — it
covers every canonical entity system-wide, so any authenticated
connection may subscribe.

## 10. Cache & freshness semantics (§12)

Unchanged from Milestone 13, reused exactly:
`FRESH`/`STALE`/`ENTITY_NOT_MAPPED`/`PROVIDER_UNAVAILABLE`/
`PROVIDER_TIMEOUT`/`RATE_LIMITED`/`INVALID_RESPONSE`/`NO_DATA`/
`UNAVAILABLE`. Every downstream consumer added this milestone
(Recommendations, Signals, Risk) receives the same `MarketSnapshotStatus`
value, never re-interpreted or coarsened. Stale is never promoted to
fresh anywhere in this milestone's own new code (see §5's FRESH-only
adapter rule, the strictest instance of this principle).

## 11. Migrations (§24)

One migration, `alembic/versions/0003_risk_market_data_coverage.py` — a
single nullable JSON column added to the existing `risk_assessments`
table. No new table. Column-existence-checked (not assumed) in both
directions: `0001_baseline_schema` drives its DDL from the *live*
`RiskAssessmentModel`, so on a database migrated for the first time after
this change the column already exists by the time `0003` runs; on a
database that already ran `0001`/`0002` before this column was added to
the model, it does not — `0003` handles both, and also tolerates
`risk_assessments` not existing at all yet (the "stamped baseline"
scenario `tests/operations/test_auth_schema_migration.py` already proves
is possible in this repository's own migration history).

Every other Milestone 14 addition (`PortfolioMarketSnapshot`,
`MarketDataCoverage`, the two new events) reuses existing in-memory
cache/service infrastructure — no additional schema was introduced
because none was genuinely required (§24's own "only add durable
relational storage if truly required").

## 12. Operations (§16)

`scripts/run_portfolio_intelligence_refresh.py` — bootstraps the app,
iterates every existing watchlist via `WatchlistService.list_watchlists()`,
and calls `PortfolioMarketSnapshotService.get_portfolio_snapshot()` for
each — printing per-portfolio fresh/stale/unavailable/unmapped counts and
individually identifying which entities need attention. Not exposed over
HTTP; container-exec only, mirroring `scripts/run_market_data_refresh.py`.

**Deliberately does not call `PortfolioIntelligenceAgent`** (the
LLM-narrated report) for every portfolio on each run — see §14 (Known
limitations / judgment calls) for why.

## 13. Configuration (§17)

**No new settings were added.** The spec named
`PORTFOLIO_INTELLIGENCE_ENABLED`/`PORTFOLIO_INTELLIGENCE_REFRESH_INTERVAL_SECONDS`
as "potential," not mandatory, and §17 itself says "only add settings
where genuinely required." Neither setting has a consumer in this
milestone's actual design — see §14 for the full reasoning. Portfolio
market-data attachment on `GET /portfolio/intelligence` reuses the
existing `MARKET_DATA_PROVIDER`/`MARKET_DATA_*` settings
(`docs/architecture/MARKET_DATA_ARCHITECTURE.md` §4) unconditionally,
the same way Research already does.

## 14. Frontend — Decision Center (additive only)

`src/types/portfolio.ts` gained `MarketSnapshotStatus`, `MarketSnapshot`,
`MarketSnapshotResult`, `MarketDataCoverageStatus`, `MarketDataCoverage`,
`MarketContribution`, `ValuationStatus`, and `PortfolioMarketSnapshot` —
mirroring the new backend fields field-for-field, all attached to
existing interfaces as optional (`?:`) properties so a report/candidate/
assessment built before this milestone type-checks unchanged. No hook
(`src/hooks/use-portfolio.ts`) needed a change — new response fields flow
through the existing React Query wrappers automatically.

A new shared `MarketFreshnessBadge`
(`src/components/market-freshness-badge.tsx`) renders
`MarketSnapshotStatus`, following the exact same `Record<Enum, className>`
pattern `PriorityBadge`/`RecommendationTypeBadge` already established —
no new badge primitive was invented.

Three existing components gained additive display only, no redesign:

- `recommendations/recommendation-list.tsx` — a new "Market" column
  (price, day change, freshness badge) per candidate row.
- `recommendations/recommendation-detail-panel.tsx` — a "Market data"
  block showing price/change/freshness plus the candidate's
  `market_contribution` in plain language (direct / indirect / none) —
  the UI-level satisfaction of §7's own "no hidden weighting, all scoring
  contributions must remain inspectable" requirement.
- `risk/risk-score-cards.tsx` — a one-line market-data-coverage note on
  the "Overall risk" card (`FULL`/`PARTIAL`/`NONE`; `NOT_EVALUATED`
  renders nothing, to avoid noise on the common pre-Milestone-14 case).
- `watchlists/portfolio-intelligence-panel.tsx` — a new "Live market
  data" section listing each `PortfolioMarketSnapshot.company_snapshots`
  entry with its price and freshness badge, when present.

Verified: `npx tsc --noEmit` clean; the full `decision-center`/
`watchlists` Vitest suites pass (58 tests, including 3 new ones asserting
the market-data UI actually renders from MSW-mocked responses).

## 15. Known limitations / documented judgment calls

- **"Indirectly through risk" reinterpreted as "indirectly through
  signals."** §7's own prose names a pathway ("indirectly through risk")
  that does not exist in this codebase's real architecture (Risk is
  strictly downstream of Recommendations — see §1). `MarketContribution`
  reports the real, existing pathway instead, flagged in its own
  docstring. Not a silent deviation.
- **No scheduled, recurring portfolio-intelligence refresh.** Unlike
  Milestone 13's `MarketDataRefreshWorkflow` (which refreshes a fixed,
  portfolio-agnostic canonical entity set on an interval), portfolios are
  arbitrary and user-created — there is no fixed set to poll — and the
  LLM-narrated report (`PortfolioIntelligenceAgent.run()`) costs a real
  Claude API call per invocation, with no cache/freshness benefit to
  calling it on a timer (nothing about its narrative goes stale the way a
  price quote does). §16's own "recompute portfolio intelligence" is
  satisfied by an on-demand operational script scoped to the live
  market-data half of "portfolio intelligence" (§12 above), not the
  LLM-narrated half — every existing `GET /portfolio/intelligence`
  request already recomputes that on demand.
- **No `PORTFOLIO_INTELLIGENCE_ENABLED`/`_REFRESH_INTERVAL_SECONDS`
  settings**, for the same reason: nothing consumes them (§13 above).
- **`RISK_ASSESSMENT_COMPLETED` still has no REST trigger** — pre-existing
  v1.0.0/Sprint 60 boundary, unchanged by this milestone (§6 above).
- **Valuation is permanently `VALUATION_UNAVAILABLE`** — no holdings
  quantity/cost-basis field exists anywhere in this codebase (§2 above);
  this is a data-availability fact, not a bug.
- **`MARKET_CAP`/`VOLATILITY`/`LIQUIDITY` risk metrics remain proxies**,
  unchanged from Milestone 13 — this milestone deliberately did not widen
  Risk's formulas to consume market data, per §5's own "existing
  calculations remain deterministic" instruction.
- Every Milestone 13 limitation (single real provider, no
  fundamentals/dividends/search, in-memory cache only, no persisted
  history) applies unchanged, since this milestone adds no new provider
  or cache.

## 16. Watchlist -> Portfolio model (§15)

Unchanged. `portfolio_id` is `watchlist_id` by the same explicit product
decision `app.api.v1.portfolio.router`'s own module docstring already
documents. No new Portfolio persistence model was introduced anywhere in
this milestone.
