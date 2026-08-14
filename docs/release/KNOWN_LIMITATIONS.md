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
