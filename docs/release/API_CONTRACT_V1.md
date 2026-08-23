# MarketMind AI — `/api/v1` Contract (Frozen at RC1)

Produced by Sprint 60. This is the authoritative, frozen contract for
`/api/v1` as of Release Candidate 1 — derived directly from the running
application's own generated OpenAPI schema (`app.main.create_app().openapi()`),
not hand-transcribed from router source, so it cannot drift from what the
server actually serves. **No breaking changes to anything documented here
are permitted without a `/api/v2`** — see `docs/release/API_VERSIONING_POLICY.md`.

## 1. Scope

49 paths, 55 operations, across 11 resource groups (OpenAPI tags):
Auth, Health, System, Watchlists, Portfolio, Company Research, Screening,
Signal Detection, Alerts, Strategy Evaluation, Backtesting,
Explainability. Real-Time Events (`/ws`) is documented separately —
`docs/architecture/WEBSOCKET_FRAMEWORK.md` — since it is not a
request/response REST resource and has its own message-level contract.

`/api/v1/auth/*` (login/refresh/logout) is a **post-freeze, additive**
extension — added for the frontend's Milestone 1, which needed a REST
entry point to the already-existing `AuthenticationService` (Sprint 56)
that had never been exposed over HTTP. It is a pure addition (three new
paths, no existing path/method/response shape touched), so it does not
require a `/api/v2` under §6's policy.

`PATCH /watchlists/{watchlist_id}/companies/{ticker}/notes` is a second
**post-freeze, additive** extension — added for the frontend's Milestone
3, which needed a way to edit a company's notes after adding it.
`WatchlistService.update_notes()` existed since the watchlist service
was first built but was never reachable over REST. Same reasoning as
the Auth addition: one new path, nothing existing touched. Milestone 3
also added a `name` filter param to `GET /watchlists`/`GET /portfolio`
(no new path — an additive query param on an existing one).

`POST /screening/profiles/{profile_id}/duplicate` is a third
**post-freeze, additive** extension — added for the frontend's Milestone
4, which needed to duplicate a saved screening profile.
`ScreeningEngine.duplicate_profile()` existed since the engine was first
built but was never reachable over REST. Milestone 4 also added a `name`
filter param to `GET /screening/profiles` (no new path), mirroring the
Milestone 3 watchlist `name` filter for the identical reason.

## 2. Request schema stability

Every request body is a `pydantic.BaseModel` with `model_config =
ConfigDict(extra="forbid")` — an unknown field is always a `422`, never
silently ignored, across every one of the 18 endpoints that accept a
body (verified by `tests/api/v1/test_contract.py`). Path/query
identifiers are typed `uuid.UUID` (automatic `422` on
malformed input) or `Path(pattern=...)`-constrained strings (ticker
format) — never a hand-written validator duplicating what Pydantic/FastAPI
already do. (23 endpoints accept a body as of the profile-duplication
addition, up from 18 at the original freeze — see §1 for all three
post-freeze additions.)

## 3. Response schema stability

Every response is one of exactly three envelope shapes
(`app.api.v1.schemas.common`), unchanged since Sprint 55:

```json
// SuccessResponse[T] — a single resource
{ "data": { /* T */ }, "meta": { "request_id", "timestamp", "api_version" } }

// PaginatedResponse[T] — a list resource
{ "data": [ /* T, T, ... */ ], "total", "page", "page_size", "meta": {...} }

// ErrorResponse / ValidationErrorResponse — any error (see §5)
{ "error": "...", "message": "...", "meta": {...} }
```

`data`/list items always reuse an existing domain model directly
(`Alert`, `Watchlist`, `RecommendationResult`, ...) wherever the domain
model's own shape already fits the wire format — never a redundant,
independently-drifting HTTP-specific reshaping. The only schemas
introduced purely for HTTP are ones no domain model represents at all
(e.g. `VersionResponse`, `CompanyResearchReportEnvelope`,
`ScreeningRunEnvelope` — each documented in its own package's schema
module).

One deliberate, documented exception to the "DELETE returns 204" rule:
`DELETE /watchlists/{watchlist_id}/companies/{ticker}` returns `200`
with the updated `Watchlist` (not `204`) — removing one company still
leaves a resource (the watchlist) worth returning, unlike deleting the
watchlist itself. This is intentional, not an inconsistency.

One equivalent, documented exception on the `POST` side: `POST
/auth/logout` returns `204` (not `201`) — it revokes a token, leaving
nothing to return, the same "genuinely no body" reasoning `DELETE`
already gets elsewhere in this contract.

A third, v1.2 Priority 8 exception on the `POST` side: `POST
/portfolio/{portfolio_id}/analysis` returns `202` (not `201`) — it
dispatches `InitialPortfolioAnalysisService.ensure_initial_analysis()` as
a `BackgroundTasks` job and returns immediately, before the job runs;
`201` (resource created/action *executed*) would be a false claim about
what has actually happened at response time. `202 Accepted` is the
standard HTTP status for exactly this "accepted for processing, not yet
complete" case — genuinely different from both `201` (synchronous,
complete by the time of response) and `204` (no body at all; this
response does have a body — the pre-dispatch `InitialAnalysisState`).

## 4. Status codes

| Code | Meaning | Where |
|---|---|---|
| `200` | Success — `GET`, `PATCH`, and the one `DELETE` noted above | every read/update endpoint |
| `201` | Success — resource created / action executed | every `POST` except the two noted below |
| `202` | Success — accepted, processing continues in the background | `POST /portfolio/{portfolio_id}/analysis` |
| `204` | Success — resource deleted (or revoked), no body | every other `DELETE` (4 endpoints), plus `POST /auth/logout` |
| `401` | No authenticated principal | `require_policy`, every protected endpoint |
| `403` | Authenticated, but the policy denies | `require_policy`, every protected endpoint |
| `404` | Unknown route, or any `*NotFoundError` domain exception | centralized `handle_domain_error`/`handle_http_exception` |
| `409` | Any `Duplicate*Error`/`*AlreadyExists*` domain exception | centralized `handle_domain_error` |
| `422` | Request validation failure (body/query/path) | every endpoint (FastAPI/Pydantic) |
| `500` | Unhandled exception (message never leaked to the client) | last-resort catch-all |
| `503` | A dependency provider found nothing configured on `app.state` | every endpoint with a service dependency |

401/403/404/409/500/503 are **not** declared per-operation via OpenAPI
`responses={}` blocks — they are handled once, centrally
(`app.api.v1.exception_handlers.handlers.register_exception_handlers`),
and documented once, in prose, here and in
`docs/architecture/API_ARCHITECTURE.md` §4, rather than duplicated across
49 paths' `responses=` declarations. This is a deliberate choice, not a
gap: `tests/api/v1/test_contract.py` verifies the *actual behavior*
(a real 404/409/422 response has the documented shape) rather than a
static per-operation OpenAPI declaration, which would drift from
`handle_domain_error`'s real inference logic the moment a new domain
exception subclass was added.

## 5. Error format

```json
// ErrorResponse
{ "error": "not_found", "message": "No watchlist found with id '...'.", "meta": {...} }

// ValidationErrorResponse (422 only)
{
  "error": "validation_error", "message": "Request validation failed.",
  "details": [ { "location": ["body", "name"], "message": "Field required", "type": "missing" } ],
  "meta": {...}
}
```

`error` is always one of: `not_found`, `method_not_allowed`,
`service_unavailable`, `conflict`, `domain_error`, `validation_error`,
`http_error`, `internal_error` — this set is closed and has not changed
since Sprint 55.

## 6. Versioning consistency

Every path is prefixed `/api/v1` (`APISettings.v1_prefix`, read once in
`app.main.create_app`, never hardcoded per-router). No endpoint anywhere
under `/api/v1` bypasses the prefix. `/api/v1/version` reports the
running application's own version string. A breaking change to any
contract element in this document requires a sibling `/api/v2` package —
see `docs/release/API_VERSIONING_POLICY.md`.

## 7. Authentication & authorization consistency

Every endpoint except `GET /api/v1/health`, `/ready`, `/version`,
`/configuration`, `/capabilities`, `/services`, and `POST
/auth/login`/`/auth/refresh` requires a valid Bearer token (`401` without
one) and a specific permission string evaluated via `RequirePermission`
(`403` if the principal lacks it) — no exceptions, no inline role checks
anywhere in any router. See `docs/architecture/AUTHENTICATION_ARCHITECTURE.md`
and each domain's own architecture doc for the full permission catalog.
`login`/`refresh` are unauthenticated by necessity — a Bearer token is
what they *issue*, not what they require (`refresh` takes a refresh
token in its request body, not a header — the `Authorization: Bearer`
header is reserved for access tokens specifically). `POST /auth/logout`
requires authentication like everything else — it uses
`RequireAuthenticated()`, not a permission string, since revoking your
own session needs no finer-grained permission.

## 8. Full endpoint catalog

Derived from the live OpenAPI schema (`tags`, `operationId`, both
FastAPI-generated and stable as long as the route's path/method/function
name don't change — none will, post-freeze).

| Method | Path | Tag |
|---|---|---|
| POST | `/api/v1/auth/login` | Auth |
| POST | `/api/v1/auth/refresh` | Auth |
| POST | `/api/v1/auth/logout` | Auth |
| GET | `/api/v1/health` | Health |
| GET | `/api/v1/ready` | Health |
| GET | `/api/v1/version` | System |
| GET | `/api/v1/configuration` | System |
| GET | `/api/v1/capabilities` | System |
| GET | `/api/v1/services` | System |
| GET | `/api/v1/watchlists` | Watchlists |
| POST | `/api/v1/watchlists` | Watchlists |
| GET | `/api/v1/watchlists/{watchlist_id}` | Watchlists |
| PATCH | `/api/v1/watchlists/{watchlist_id}` | Watchlists |
| DELETE | `/api/v1/watchlists/{watchlist_id}` | Watchlists |
| POST | `/api/v1/watchlists/{watchlist_id}/companies` | Watchlists |
| DELETE | `/api/v1/watchlists/{watchlist_id}/companies/{ticker}` | Watchlists |
| PATCH | `/api/v1/watchlists/{watchlist_id}/companies/{ticker}/notes` | Watchlists |
| GET | `/api/v1/watchlists/{watchlist_id}/snapshot` | Watchlists |
| GET | `/api/v1/portfolio` | Portfolio |
| GET | `/api/v1/portfolio/{portfolio_id}` | Portfolio |
| GET | `/api/v1/portfolio/summary` | Portfolio |
| GET | `/api/v1/portfolio/intelligence` | Portfolio |
| GET | `/api/v1/portfolio/risk` | Portfolio |
| GET | `/api/v1/portfolio/recommendations` | Portfolio |
| POST | `/api/v1/portfolio/recommendations` | Portfolio |
| POST | `/api/v1/research/company` | Company Research |
| POST | `/api/v1/research/batch` | Company Research |
| GET | `/api/v1/research/{request_id}` | Company Research |
| GET | `/api/v1/screening/profiles` | Screening |
| POST | `/api/v1/screening/profiles` | Screening |
| POST | `/api/v1/screening/profiles/{profile_id}/duplicate` | Screening |
| PATCH | `/api/v1/screening/profiles/{profile_id}` | Screening |
| DELETE | `/api/v1/screening/profiles/{profile_id}` | Screening |
| POST | `/api/v1/screening/run` | Screening |
| GET | `/api/v1/screening/results/{result_id}` | Screening |
| GET | `/api/v1/signals/definitions` | Signal Detection |
| POST | `/api/v1/signals/definitions` | Signal Detection |
| PATCH | `/api/v1/signals/definitions/{definition_id}` | Signal Detection |
| DELETE | `/api/v1/signals/definitions/{definition_id}` | Signal Detection |
| POST | `/api/v1/signals/evaluate` | Signal Detection |
| GET | `/api/v1/signals/results/{result_id}` | Signal Detection |
| GET | `/api/v1/alerts` | Alerts |
| GET | `/api/v1/alerts/{alert_id}` | Alerts |
| POST | `/api/v1/alerts/evaluate` | Alerts |
| GET | `/api/v1/strategies` | Strategy Evaluation |
| POST | `/api/v1/strategies` | Strategy Evaluation |
| PATCH | `/api/v1/strategies/{strategy_id}` | Strategy Evaluation |
| DELETE | `/api/v1/strategies/{strategy_id}` | Strategy Evaluation |
| POST | `/api/v1/strategies/evaluate` | Strategy Evaluation |
| GET | `/api/v1/strategies/results/{result_id}` | Strategy Evaluation |
| POST | `/api/v1/backtests` | Backtesting |
| GET | `/api/v1/backtests/{run_id}` | Backtesting |
| GET | `/api/v1/backtests/{run_id}/results` | Backtesting |
| POST | `/api/v1/explainability` | Explainability |
| GET | `/api/v1/explainability/{request_id}` | Explainability |

## 9. Known, accepted gaps (carried forward, not fixed this sprint)

Per this sprint's own constraint ("Do NOT modify business logic unless
absolutely required to fix a production defect") — none of these are
production defects, so none were touched:

- `RISK_ASSESSMENT_COMPLETED` (WebSocket event) has no REST creation
  trigger — `GET /portfolio/risk` is read-only by Sprint 57 design.
- The three `InMemoryResultStore`-backed `GET .../{id}` endpoints
  (Company Research, Screening, Signal Detection results) are in-process
  only — not shared across app instances, lost on restart.
- No endpoint exists for `AlertRule` CRUD — rules must already exist
  before `POST /alerts/evaluate` can reference them by id.

Both are documented in full in `docs/architecture/INTELLIGENCE_API.md`
and `docs/architecture/WEBSOCKET_FRAMEWORK.md`; repeated here only so the
frozen contract's limits are visible in one place.
