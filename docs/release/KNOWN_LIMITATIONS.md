# MarketMind AI — Known Limitations (v1.0.0)

Every item below is a deliberate, documented scope boundary — not an
oversight. Each links to the sprint/milestone/document that explains the
reasoning in full. §"Backend" is unchanged since RC1; §"Frontend" and
§"Deployment" are new for v1.0.0.

## Backend

## No live market data or broker integration

By explicit constraint across multiple sprints (most recently reaffirmed
in Sprint 60's own "MUST NOT" list). `MarketDataProvider` is a mock
implementation; there is no real quote feed and no order execution of
any kind. This is a market *intelligence* platform, not a trading one.

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

`BaseEmbeddingProvider` has zero concrete implementations — this was
already true before Sprint 60 and remains true; features depending on it
degrade to `503`.

## OpenAPI does not declare per-operation error responses

401/403/404/409/500/503 are handled once, centrally, and documented once
in prose (`docs/release/API_CONTRACT_V1.md` §4) rather than declared via
a `responses={}` block on each of 50 operations — a deliberate choice to
avoid 50 duplicated, driftable declarations of the same centralized
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
