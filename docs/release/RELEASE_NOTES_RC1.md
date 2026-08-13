# MarketMind AI — Release Candidate 1 (RC1) Release Notes

Produced by Sprint 60, the final planned backend/API sprint. **API v1 is
frozen as of this release** — see `docs/release/API_VERSIONING_POLICY.md`.

## What's in RC1

**Backend (Sprints 1-54, frozen):** the full multi-agent market
intelligence engine — screening, signal detection, alerts, portfolio
recommendations, strategy evaluation, risk analytics, backtesting,
explainability, company research, portfolio intelligence, knowledge
ingestion, the morning research pipeline, and the scheduler. See
`docs/architecture/BACKEND_ARCHITECTURE.md`.

**REST API (Sprints 55-58):** a versioned `/api/v1` surface — 44 paths,
50 operations — exposing every domain engine's own service methods
directly, with no duplicated business logic. Bearer-token authentication
and policy-based authorization on every non-public endpoint. See
`docs/release/API_CONTRACT_V1.md` for the full frozen contract and
`docs/architecture/{API_ARCHITECTURE,AUTHENTICATION_ARCHITECTURE,
WATCHLIST_PORTFOLIO_API,INTELLIGENCE_API}.md` for how it was built.

**Real-Time Events (Sprint 59):** a single authenticated WebSocket
(`/ws`) delivering already-completed backend activity — alerts,
backtests, recommendations, strategy evaluations, explainability, and
health-state changes — in real time. See
`docs/architecture/WEBSOCKET_FRAMEWORK.md`.

**Production hardening (Sprint 60, this release):**

- API contract frozen and documented (`docs/release/API_CONTRACT_V1.md`).
- OpenAPI generation validated: Bearer security metadata on every
  protected operation, unique operation IDs, tags, descriptions, and
  request/response examples across every schema.
- Rate limiting abstraction (`app.api.rate_limiting`) — provider-independent
  interfaces for per-user/per-IP/per-route limits with burst and
  sustained allowances. No concrete implementation ships yet.
- Idempotency abstraction (`app.api.idempotency`) — `Idempotency-Key`
  header support and a duplicate-request-detection interface. No
  persistence implementation ships yet.
- Security response headers middleware — `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` always on;
  `Content-Security-Policy` and `Strict-Transport-Security` configurable,
  disabled by default (see `docs/release/PRODUCTION_CONFIGURATION_GUIDE.md`).
- Performance benchmarks for startup, health, auth middleware, policy
  evaluation, repository access, recommendation generation, and
  WebSocket connection establishment (measure-only, no tuning performed).
- End-to-end integration tests exercising a full cross-domain workflow
  (watchlist → recommendation → strategy → backtest → explainability →
  alert, with live WebSocket notifications for each step).
- Full documentation set for operating this release — this document plus
  the six others listed in `docs/release/`.

## Test suite

2700+ tests, zero known failures, zero regressions introduced this
sprint. See `docs/release/RELEASE_CHECKLIST.md` §6 for how to reproduce
this locally.

## Upgrading to RC1

There is no prior tagged release — RC1 is the first. See
`docs/release/UPGRADE_POLICY.md` for how future releases will be handled
now that `/api/v1` is frozen.

## Known limitations

See `docs/release/KNOWN_LIMITATIONS.md` for the full list. Headline
items: no live market data provider, no broker integration, no
distributed rate limiting/idempotency implementation yet, `/ws` is
single-process only (no distributed event bus), one WebSocket event type
(`RISK_ASSESSMENT_COMPLETED`) has no REST trigger endpoint yet.

## What's explicitly out of scope for RC1

Per this sprint's own constraints: no new investment features, no
changes to any business logic/algorithm (recommendation, strategy,
risk), no GraphQL, no broker integrations, no live market data
providers. These are possible future directions, not gaps in this
release.
