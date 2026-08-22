# MarketMind AI — Known Limitations (v1.0.0)

Every item below is a deliberate, documented scope boundary — not an
oversight. Each links to the sprint/milestone/document that explains the
reasoning in full. §"Backend" is unchanged since RC1; §"Frontend" and
§"Deployment" are new for v1.0.0.

## Backend

## No live market data or broker integration

By explicit constraint across multiple sprints (most recently reaffirmed
in Sprint 60's own "MUST NOT" list). `MarketDataProvider` is a mock
implementation by default; there is no order execution of any kind, and
none is planned — this is a market *intelligence* platform, not a
trading one. **Live market data itself resolved post-v1.0 (Milestone
13)**: a real `MarketDataProvider` (Yahoo Finance) is now selectable via
`MARKET_DATA_PROVIDER=yahoo_finance` — see
`docs/architecture/MARKET_DATA_ARCHITECTURE.md`. `MockMarketDataProvider`
remains the default (no behavior change for an existing deployment that
doesn't opt in), and broker integration / order execution remain
permanently out of scope, unaffected by this.

## Rate limiting is not enforced

`app.api.rate_limiting` (Sprint 60) ships interfaces only — `RateLimiter`
has zero concrete implementations. No request in RC1 is actually
rate-limited by this application. See `docs/release/SECURITY_CONSIDERATIONS.md`.

## Idempotency is not enforced

`app.api.idempotency` (Sprint 60) ships interfaces only — `IdempotencyStore`
has zero concrete implementations. Sending the same `POST` twice (even
with an `Idempotency-Key` header) executes the underlying operation
twice; the header is currently read and ignored beyond that.

## `/ws` is single-process, in-memory only

No distributed event bus (Kafka/RabbitMQ/Redis Streams — explicitly
excluded, Sprint 59). Running multiple application replicas means a
WebSocket client connected to replica A never sees an event published
from replica B. See `docs/architecture/WEBSOCKET_FRAMEWORK.md` §9 for
the integration point a future sprint would use to add one without
changing `ConnectionManager`'s own logic.

## `/ws` has no message persistence or replay

A client that connects after an event was published never sees it —
there is no buffer, queue, or history (Sprint 59's own explicit
constraint). A client must be connected *before* an event happens to
receive it.

## `RISK_ASSESSMENT_COMPLETED` has no REST trigger

No endpoint in `/api/v1` calls `RiskAnalyticsService.assess_portfolio()`
— `GET /portfolio/risk` is a read-only lookup of an already-stored
assessment (Sprint 57's own design decision), and Sprint 58/59/60 each
inherited "REST API surface is feature complete"/frozen constraints that
rule out adding a creation endpoint retroactively. The event model and
publisher method exist and are fully tested; nothing currently invokes
them in production.

## Three `GET .../{id}` endpoints are backed by an in-process cache, not real persistence

Company Research reports, screening run results, and signal evaluation
results (`app.api.v1.schemas.result_store.InMemoryResultStore`, Sprint
58) are cleared on restart and not shared across replicas. Their
underlying domain services genuinely have no persistence of their own
(a pure/stateless evaluator, or a read-only agent) — this is a thin,
zero-business-logic HTTP-layer cache filling that gap, not a production
data store. See `docs/architecture/INTELLIGENCE_API.md` §2.

## No `AlertRule` CRUD endpoint

`POST /alerts/evaluate` can only reference `AlertRule`s that already
exist — created via `AlertService.create_rule()` directly (e.g. a
seeding script), not through any REST endpoint. Out of scope for every
sprint that has touched the Alert API so far.

## No embedding provider

`BaseEmbeddingProvider` had zero concrete implementations as of v1.0.0 —
already true before Sprint 60 and true through the v1.0.0 freeze;
features depending on it degraded to `503`. **Resolved post-v1.0**:
Milestone 11 (`docs/architecture/MARKET_INTELLIGENCE_INGESTION.md`)
added `LocalEmbeddingProvider`, a real local-model implementation. This
does not retroactively change what v1.0.0 itself shipped with — recorded
here as the historical v1.0.0 gap, with a forward pointer to where it was
actually fixed.

## OpenAPI does not declare per-operation error responses

401/403/404/409/500/503 are handled once, centrally, and documented once
in prose (`docs/release/API_CONTRACT_V1.md` §4) rather than declared via
a `responses={}` block on each of 55 operations — a deliberate choice to
avoid 55 duplicated, driftable declarations of the same centralized
logic. Swagger UI will not show example 4xx/5xx bodies per endpoint as a
result.

## No OpenAPI request/response size limits documented

There is no documented maximum request body size or array length beyond
each domain model's own `Field(min_length=...)` constraints. See
`docs/release/SECURITY_CONSIDERATIONS.md`'s input validation section.

## Single-region, single-database

No multi-region, read-replica, or sharding support of any kind — one
PostgreSQL instance, addressed by one `DATABASE_URL`. Out of scope for
this platform's current maturity.

## Frontend

No admin UI for user/role/permission management — provisioning a user
is a direct database/seeding-script operation
(`docs/release/ADMINISTRATOR_GUIDE.md`). No self-service signup or
password reset. Notification Center and activity feed history are
session-only (no WebSocket replay — matches the backend's own `/ws`
limitation above). No server-side aggregation of frontend errors — an
`ErrorBoundary` logs to the browser console only, by design (no new
telemetry vendor, `docs/release/OBSERVABILITY_VERIFICATION.md`).

The shared `Button` component (Milestone 9) was adopted in new code and
the highest-leverage existing call sites only — most of the app's ~20
other buttons still use the pre-Milestone-9 inline styling pattern, a
deliberately bounded retrofit. None of the app's 13 chart components
provide an accessible tabular-data fallback (Recharts' own
`accessibilityLayer` gives per-point keyboard/tooltip narration, not an
at-a-glance summary). Keyboard-shortcut key bindings can collide if a
user manually rebinds two actions to the same key — the first-defined
action wins deterministically; no collision-prevention UI exists.
`TopNav`'s mobile layout received spacing adjustments only, not a
structural redesign (e.g. collapsing the theme toggle to icon-only) —
that's a product/design decision, not an engineering one, and was left
for a future milestone. Full detail on every frontend-specific
deferred item: `docs/frontend/MILESTONE_9.md` §7.

## Deployment

`chromadb` 1.5.9 (this project's currently-declared minimum,
`chromadb>=0.5.0`) has an unpatched pre-authentication code-injection
advisory (`PYSEC-2026-311`) on its own HTTP API — no fixed version
exists yet. Mitigated at the deployment level: ChromaDB's port is not
published outside the Docker network in `docker-compose.prod.yml`.
Track this advisory and upgrade `chromadb` once a fix ships. See
`docs/release/SECURITY_REVIEW_V1.md`.

Content-Security-Policy is disabled by default on both the backend and
the frontend's nginx config — enabling it safely requires tuning to
each specific deployment's own origins (see
`docs/release/SECURITY_REVIEW_V1.md` for a ready-to-adapt value).

## Market Intelligence Ingestion (Milestone 11, post-v1.0)

Not part of v1.0.0 — see
`docs/architecture/MARKET_INTELLIGENCE_INGESTION.md` for the full design.
Its own known limitations:

- ~~**No real entity/company resolution.** Every ingested knowledge
  record is recorded honestly as `entity_resolved: False` — Research
  still matches purely by semantic similarity over article text, the
  same mechanism it always used.~~ **Resolved post-v1.0 (Milestone 12)**:
  see the "Entity Resolution & Company Intelligence" section below and
  `docs/architecture/ENTITY_RESOLUTION.md`. Recorded here as the
  historical Milestone 11 gap, with a forward pointer to where it was
  actually fixed — this does not retroactively change what Milestone 11
  itself shipped with.
- **`ChromaKnowledgeRepository` doesn't consume the pipeline's own
  computed embedding vectors** — it upserts raw text, and ChromaDB's own
  configured embedding function computes (and actually stores) the
  vector independently. `MorningPipeline`'s embedding stage still runs
  and its results still feed observability counts, but the vector it
  computes is not the one ultimately stored. Not a correctness bug (both
  computations use the same underlying model) — a duplicate-work quirk,
  left for a future milestone.
- **Relational persistence is not wired up** — only the ChromaDB-only
  `ChromaKnowledgeRepository` path is active; `RelationalRecord`/
  `PostgresKnowledgeRepository`/`CompositeKnowledgeRepository` exist and
  are tested but are not part of this milestone's `app.bootstrap` wiring.
- **No dedicated market-news aggregation surface.** Ingested news
  surfaces only within an individual Research report (unchanged from
  v1.0.0) — a deliberate scope decision for this milestone, not an
  oversight; the milestone's core requirement (Research automatically
  benefiting from newly ingested knowledge) was already satisfied without
  one.
- **Single-process scheduler**, same characteristic as `/ws` (above):
  running multiple backend replicas means each independently schedules
  its own ingestion runs, with no distributed lock. Idempotent upsert
  (§5 of the architecture doc) makes concurrent/overlapping runs safe,
  just redundant — not fixed here.

## Entity Resolution & Company Intelligence (Milestone 12, post-v1.0)

Not part of v1.0.0 — see `docs/architecture/ENTITY_RESOLUTION.md` for the
full design. Its own known limitations:

- **Static reference set.** Only the companies in
  `app.services.market_intelligence.engine.COMPANY_KEYWORDS` (12 as of
  this milestone) can ever resolve — no external company database, no
  fuzzy/ML-based matching. A real company not yet in the set correctly
  stays `UNRESOLVED`, never guessed.
- **No cross-lingual matching.** Company names/aliases are matched as
  literal English-language strings only.
- **Research report sections 5-6 (`sector_analysis`/`country_exposure`,
  driven by the pre-existing `RelationshipEngine`'s own keyword-based
  text detection) are not reconciled with the new resolved-entity
  `company_overview.sector`/`.country` fields** (a direct reference-data
  lookup) — both are honest, independently-computed signals; a report
  can show a populated `company_overview.sector` while still carrying a
  `NO_SECTOR_CONTEXT` risk flag. Reconciling the two would mean changing
  `RelationshipEngine`'s own logic, which was out of this milestone's
  scope.
- **Single-process, no distributed backfill coordination.** Running
  `scripts/run_entity_backfill.py` from multiple places concurrently is
  safe (resolution is idempotent) but redundant — same characteristic
  already documented for the Milestone 11 scheduler above.

## Live Market Data & Price Intelligence (Milestone 13, post-v1.0)

Not part of v1.0.0 — see `docs/architecture/MARKET_DATA_ARCHITECTURE.md`
for the full design. Its own known limitations:

- **Single real provider, no automatic fallback.** Only Yahoo Finance's
  public chart endpoint is integrated; if it becomes unavailable or
  changes shape, there is no automatic failover to a second vendor.
- **No fundamentals/dividends/earnings/search from the real provider** —
  only current quotes and historical OHLCV are backed by real data when
  `MARKET_DATA_PROVIDER=yahoo_finance`; every other `MarketDataProvider`
  method raises explicitly rather than fabricating a response.
- **In-memory cache only** — `InMemoryMarketSnapshotCache` is
  process-local, lost on restart, and not shared across replicas running
  multiple backend instances — same characteristic already documented
  for the Milestone 11 scheduler / Milestone 12 backfill above.
- ~~**No Portfolio/Risk/Recommendation/Strategy/Backtesting
  integration.** Deliberately deferred — no existing consumer's contract
  explicitly expects market data yet (verified by inspection); forcing an
  integration would mean changing formulas never designed to consume
  it.~~ **Resolved post-v1.0 (Milestone 14)**: see the "Portfolio
  Intelligence & Decision Integration" section below and
  `docs/architecture/PORTFOLIO_INTELLIGENCE.md`. Historical
  Analysis/Backtesting remain unintegrated. Recorded here as the
  historical Milestone 13 gap, with a forward pointer to where most of it
  was actually addressed — this does not retroactively change what
  Milestone 13 itself shipped with.
- **No persisted market-snapshot history.** Only the latest snapshot per
  canonical entity is cached; no time-series of past snapshots is stored.

## Portfolio Intelligence & Decision Integration (Milestone 14, post-v1.0)

Not part of v1.0.0 — see `docs/architecture/PORTFOLIO_INTELLIGENCE.md`
for the full design. Its own known limitations:

- **Valuation is permanently `VALUATION_UNAVAILABLE`.** `WatchlistItem`
  carries no quantity/position-size/market-value/weight field anywhere in
  this codebase — an aggregate portfolio value, P&L, return, or benchmark
  comparison is never computed, never fabricated.
- **`MARKET_CAP`/`VOLATILITY`/`LIQUIDITY` risk metrics remain proxies.**
  Risk's own formulas were deliberately left unchanged — market data
  contributes only an informational `market_data_coverage` field, never a
  scoring input.
- **`RISK_ASSESSMENT_COMPLETED` still has no REST trigger** — the same
  pre-existing v1.0.0/Sprint 60 boundary documented above, unaffected by
  this milestone.
- **No scheduled, recurring portfolio-intelligence refresh.** Unlike the
  Milestone 13 market-data refresh (a fixed, portfolio-agnostic entity
  set on an interval), portfolios are arbitrary and user-created — there
  is no fixed set to poll — and the LLM-narrated report costs a real
  Claude API call per invocation with no freshness benefit to polling it.
  `scripts/run_portfolio_intelligence_refresh.py` is on-demand only, and
  intentionally scoped to live market data, not the LLM narrative (every
  `GET /portfolio/intelligence` request already recomputes that on
  demand).
- **No `PORTFOLIO_INTELLIGENCE_ENABLED`/`_REFRESH_INTERVAL_SECONDS`
  settings.** Nothing in this milestone's actual design consumes them —
  see the architecture doc's own §13/§14 for the full reasoning.
- **"Indirectly through risk" (as this milestone's own spec names it) is
  not a real pathway in this codebase's architecture** — Risk is strictly
  downstream of Recommendations and cannot feed back into it.
  `RecommendationCandidate.market_contribution` reports the real,
  existing pathway instead ("indirectly through signals"), flagged as a
  documented interpretation in its own docstring.
- Every Milestone 13 market-data limitation above (single provider,
  in-memory cache, no persisted history) applies unchanged — this
  milestone adds no new provider or cache.

## Continuous Intelligence & Decision Automation (Milestone 15, post-v1.0)

Not part of v1.0.0 — see `docs/architecture/CONTINUOUS_INTELLIGENCE.md`
for the full design. Its own known limitations (several resolved by
Milestone 16 — see that section below):

- ~~Strategy state transitions are not detected automatically.~~
  **Resolved in Milestone 16** — see below.
- **Risk/Recommendation changes require something else to have already
  recomputed them.** This milestone never calls `assess_portfolio()`/
  `generate_recommendations()` itself — no automatic evidence-sourcing
  pipeline exists anywhere in this codebase to feed them. A portfolio
  whose risk/recommendations are never recomputed by any existing
  pathway (user action or otherwise) will never produce a decision-context
  notification, no matter how long the scheduled cycle runs. **Still true
  in Milestone 16** — out of scope for a reliability-hardening milestone.
- **No per-user watchlist ownership, still.** Same pre-existing
  characteristic Milestone 14 already documented — scope is enforced by
  permission + `correlation_id` only, not a new ownership model (adding
  one would be an architecture redesign, out of scope for this milestone).
- ~~In-memory previous-state and suppression tracking, lost on restart.~~
  **Resolved when PostgreSQL is reachable, in Milestone 16** — see below;
  remains true only when no durable repository is configured.
- **Multi-replica event fan-out remains per-process.** Milestone 16 adds
  cross-process cycle locking and durable suppression (below), so two
  replicas no longer both run a cycle or both emit the same duplicate —
  but WebSocket delivery itself is still per-process: a notification
  published by the replica that ran the cycle only reaches clients
  connected to *that* replica, not clients connected to a different one.
  No distributed event bus was introduced (explicitly out of scope).

## Continuous Intelligence — Persistence & Reliability (Milestone 16, post-v1.0)

Not part of v1.0.0 — see
`docs/architecture/CONTINUOUS_INTELLIGENCE_PERSISTENCE.md` for the full
design. Hardens Milestone 15 against restart, duplicate execution, and
scheduler/process overlap. Its own known limitations:

- **State/suppression/locking are in-memory-only, and thus restart-unsafe
  and single-process-only, whenever no PostgreSQL repository is reachable
  at startup.** This is a graceful degradation (the system still
  functions, exactly as it did in Milestone 15), not a silent failure —
  `scripts/inspect_continuous_intelligence.py` reports
  `"status": "in_memory_only"` explicitly in this configuration.
- **Risk/Recommendation/Strategy changes still require something else to
  have already recomputed them** — unchanged from Milestone 15, this
  milestone hardens reliability, not evidence-sourcing.
- **No distributed event bus / multi-region infrastructure** — explicitly
  out of scope (§24). Cross-process *coordination* (locking, durable
  suppression) is now provided; cross-process *event delivery* to
  clients connected to a different replica is not — see the Milestone 15
  entry above.
- **No per-user watchlist ownership was introduced** — same as Milestone
  15's entry; the strategy-linkage fix (§12) traces a stored evaluation
  back to `RecommendationRequest.watchlist_ids` via existing references,
  never a new ownership model.
- **The canonical-entity overlay mechanism (§8) does not fetch from any
  external company/security master** — it only validates and merges
  operator-supplied, already-real company data from a local JSON file. A
  future external reference source (e.g. a real security master API)
  would need its own, separate milestone; this one only builds the
  configuration seam, not an integration.

## Production Hardening & v1.1 Release Candidate (Milestone 17, post-v1.0)

Not part of v1.0.0 — see `docs/release/RELEASE_CHECKLIST_V1_1.md` for the
full verification record. This is explicitly the final planned
engineering milestone for the v1.1 line — no new feature milestone is
planned after it. Its own known limitations:

- **A fresh/recreated container's first embedding-dependent operation is
  slow.** The local embedding provider's ONNX model
  (`all-MiniLM-L6-v2`, ~79MB) caches to `~/.cache/chroma/onnx_models/`
  inside the container, which is **not** part of the persistent
  `backend_chroma_cache` named volume (that volume only mounts
  `/app/data/cache`) — so every freshly-recreated container (not just
  every image rebuild) re-downloads the model on first use, observed
  live this milestone to extend one Continuous Intelligence cycle from
  the usual ~90-100s to several minutes. Not a functional defect (the
  cycle still completed correctly, zero failures); fixing it would mean
  changing the Docker volume/cache layout, judged out of scope for this
  release-hardening pass (no speculative rewrites, per this milestone's
  own instruction) — a real, evidence-backed candidate for a future
  Docker-layer improvement, not a code change.
- **Research and Portfolio Intelligence require a real `ANTHROPIC_API_KEY`
  to function past authentication/routing** — unchanged, pre-existing
  behavior (documented since v1.0.0), reconfirmed this milestone: with
  the placeholder key, the LLM call fails with a clean `401`, never a
  crash, and every other endpoint remains unaffected.
- **Version strings** (`backend/pyproject.toml`, `frontend/package.json`,
  the FastAPI app's own `version="1.0.0"`) were deliberately **not**
  bumped this milestone — a genuine release decision left to whoever
  performs the actual v1.1 tagging step, not a verification gap.
- Every Milestone 15/16 limitation listed above remains true and
  unchanged — this milestone is verification and hardening, not new
  capability.

## Selective Signals & High-Quality Alerts (v1.2 Priority 1)

Driven directly by the v1.1.1 real-world pilot's own P1 finding (887
alerts, one signal, every one scoring exactly `confidence=100.0`/
`score=100.0`). Full root-cause trace and fix design:
`docs/architecture/CONTINUOUS_INTELLIGENCE.md` §18. Its own known
limitations:

- ~~Cross-portfolio notification grouping is still not implemented.~~
  **Resolved in v1.2 Priority 2** — see the section immediately below
  and `docs/architecture/CONTINUOUS_INTELLIGENCE.md` §19.
  `DetectedChange.event_fingerprint`, added here, is exactly what that
  fix groups on. Recorded here as the historical Priority 1 gap, with a
  forward pointer to where it was actually closed.
- **The Signal Detection Engine's `MarketQuote` model has no continuous,
  magnitude-proportional scoring primitive** — the replacement "Live
  Price Breakout" signal graduates score via discrete, weighted
  pass/fail conditions (a 5%+ move, a liquidity floor), not a smooth
  curve — a -11% move and a -20% move both satisfy the same "did it move
  at least 5%" condition and therefore score identically. Building a
  true magnitude-proportional primitive would mean extending
  `SignalCondition`'s own evaluation semantics, judged out of scope (no
  new engine capability, per this change's own explicit instruction) —
  a real, evidence-backed candidate for a future Signal Detection
  Engine enhancement, not addressed here.
- **`POST /alerts/evaluate` still accepts any caller-supplied
  `SignalResult` at face value** — `AlertService` does not itself
  recompute or validate a `SignalResult`'s claimed `score`/`confidence`
  against its own `matched_conditions`/`failed_conditions` evidence (or
  reject one carrying no evidence at all). The concrete, reproducible
  root cause of the pilot's own finding was fully explained by the
  degenerate signal *definition* alone (§18) — no evidence of a
  hand-crafted/fabricated `SignalResult` payload was found — so adding
  an evidence-validation gate to `AlertService` was judged unnecessary
  speculative complexity for this change; the API contract itself was
  also explicitly out of scope (`/api/v1` frozen). A real gap if this
  endpoint's trust boundary is ever revisited.
- Every existing Continuous Intelligence / Signal Detection / Alert
  Engine limitation documented elsewhere in this file remains true and
  unchanged — this is a signal-quality and explainability fix, not a
  new capability or an architecture change.

## Cross-Portfolio Notification Grouping (v1.2 Priority 2)

Closes the pilot's own P2 finding using the `event_fingerprint` Priority
1 (above) introduced. Full design: `docs/architecture/CONTINUOUS_INTELLIGENCE.md`
§19. Its own known limitations:

- **Grouping is presentation-only — WS network traffic is not reduced.**
  One broadcast still goes out per surviving impacted portfolio (unchanged
  from before this milestone), to preserve narrow `correlation_id`
  subscription delivery (`docs/architecture/WEBSOCKET_FRAMEWORK.md` §4) —
  a client reading raw WS frames instead of going through this
  codebase's own Notification Center store would still see N frames for
  one event. Real traffic reduction would need a multi-value
  `correlation_id` (a subscription-matching model change) or a
  distributed fan-out layer, both explicitly out of scope (no WebSocket
  transport redesign).
- **No per-portfolio detail inside a grouped notification** — the
  summary is the underlying event's own description plus an "Affected: N
  portfolios" count; it does not (and cannot, since no such data exists
  anywhere in this codebase — Milestone 14's own permanent
  `VALUATION_UNAVAILABLE` constraint) explain how the event affects each
  portfolio differently (position size, existing holdings, etc.).
- **Grouping only ever spans copies produced by one `_route()` call** —
  by construction, every candidate fanned out from one detected change
  already shares one `event_fingerprint`, so there is no cross-cycle or
  cross-entity grouping to implement or reason about; this is not a
  scope limitation so much as the reason no new durable state was
  needed, but it does mean a *coincidentally* related pair of events
  (e.g. two different signals both about to notify the same portfolio
  seconds apart) are never merged — only truly identical underlying
  events are.
- ~~No per-user notification preferences for grouped vs. ungrouped
  delivery~~ — **superseded by v1.2 Priority 4** (below):
  `notifications.groupCrossPortfolioNotifications` now offers exactly
  this opt-out, presentation-only.

## Portfolio Decision Digest (v1.2 Priority 3)

Folds multiple *different* decision-domain changes (Risk/Recommendation/
Strategy/Signal) for the *same* portfolio, arriving within
`DECISION_DIGEST_WINDOW_MS` (5 minutes) of one another, into a single
Notification Center entry. Entirely a frontend/presentation change — no
backend code was modified, no new WS event type or payload field was
added; every field the digest needs already existed on
`PORTFOLIO_INTELLIGENCE_CHANGED`'s `DetectedChange` payload since
Milestone 15. Full design: `docs/architecture/CONTINUOUS_INTELLIGENCE.md`
§20. Its own known limitations:

- **Session-only, like every other Notification Center entry** — a
  digest's window resets on page reload/reconnect (the backend's own WS
  framework has no message replay at all — §6 — so there is no history
  to rebuild from regardless). A change that would have extended a
  pre-reload digest starts a brand-new one afterward.
- ~~The 5-minute window is not user-configurable~~ — **superseded by
  v1.2 Priority 4** (below): `notifications.decisionDigestWindowMinutes`
  (1-30, default 5) is now a Workspace Settings preference.
- **Only combines changes that already share one `_route()` call's own
  portfolio scope** — this is not a general "notification batching"
  feature; two events for genuinely unrelated portfolios, or two events
  for the same portfolio more than 5 minutes apart, are never combined,
  by design.
- **No true per-change action affordance inside a digest** — clicking a
  digest deep-links to `/decisions/$portfolioId` (the portfolio's own
  Decision Center), same as a single decision entry always has; there is
  no way to jump directly to, say, just the Strategy tab from a digest
  entry listing a Strategy change among others.

## Notification & Intelligence Preferences (v1.2 Priority 4)

Makes the Priority 2 grouping toggle, the Priority 3 digest window, and
the realtime toast pop-up user-configurable, reusing Milestone 8's
existing client-side `preferences-store.ts`/`preferences-io.ts`
architecture unchanged — no new settings store, no new settings page, no
backend change, no WebSocket protocol change, no PostgreSQL schema. Full
design: `docs/architecture/CONTINUOUS_INTELLIGENCE.md` §21;
`docs/frontend/MILESTONE_8.md` §8. Its own known limitations:

- **Presentation-only by construction, same as the features it
  configures** — none of the 3 new preferences can suppress an alert,
  change what reaches a portfolio, or reduce WS network traffic; a client
  reading raw WS frames instead of going through this codebase's own
  Notification Center store sees the same frames regardless of any of
  these settings.
- **`decisionDigestWindowMinutes` is capped at 30 minutes** — a
  deliberately bounded range (1-30), not the arbitrary window a user
  might want; matches the milestone's own explicit range instruction, not
  a technical limit.
- **A digest's window is locked in at creation, not live-updated** — by
  design (an already-open digest must not behave erratically if the
  setting changes mid-window), but it does mean a setting change is never
  visible on an in-progress digest, only on ones started afterward — a
  user might reasonably expect an immediate effect and not get one until
  the next digest.
- **No per-domain (market/news/decisions) versions of these 3
  preferences** — grouping, digest window, and toast suppression are each
  a single global setting, not configurable per notification category.
  The pre-existing `enabledCategories` array remains the only per-domain
  control, and it is a full on/off, not a presentation nuance.
- **Desktop notifications remain their own separate, pre-existing
  preference** (`desktopNotificationsEnabled`, Milestone 8) — `showRealtimeToasts`
  intentionally does not gate them; no new browser-permission
  infrastructure was added or needed here.

## Company-Focused News Sources & Ingestion Quality (v1.2 Priority 6)

Extends `RSS_FEED_URLS` from 1 general feed to 10 (4 official Nasdaq
category feeds + 5 official company IR feeds), fixes a real provenance
gap (`item.source_metadata` was computed but never reached the persisted
record), adds cross-feed duplicate-URL detection, and adds per-feed
source health reporting. Full design:
`docs/architecture/MARKET_INTELLIGENCE_INGESTION.md` §13;
`docs/architecture/ENTITY_RESOLUTION.md` §15. Its own known limitations:

- **Only 5 of 12 canonical companies have a dedicated IR feed** (Dell,
  Salesforce, Workday, Reddit, Sandisk) — the other 7 rely entirely on
  general-media pickup via the Nasdaq category feeds. This was a
  deliberate scope decision (the mega-cap 7 are already well-covered by
  general media; a feed-per-company for all 12 was judged operationally
  unnecessary), not a coverage guarantee.
- **Cross-run source health history is log-based, not a persisted
  store** — "last successful fetch," "last failure," and "failure rate
  over time" require reading the existing `rss_feed_fetched`/
  `rss_feed_fetch_failed` structured logs (§13's own documented `grep`
  pattern); there is no queryable API/dashboard for this in this release.
- **The entity overlay gained exactly one entry (Walmart/WMT)** — the
  ranked-unresolved-entity analysis found a long tail of macro/policy
  topics and personal-finance advice phrasing that is not a company at
  all, not a large pool of safe additions. Expanding company-specific
  evidence further requires more company-focused sources (this
  milestone's own §13), not more overlay entries.
- **Alert priority is still a fixed constant, not derived from signal
  score/confidence** — identified in v1.2 Priority 5 (§6 of that
  session's own report) and deliberately not addressed here; remains a
  separate, focused future task.
- Every existing Market Intelligence Ingestion / Entity Resolution
  limitation documented elsewhere in this file remains true and unchanged
  — this is a source-quality and provenance fix, not an architecture
  change.
