# MarketMind AI — REST API Foundation (`/api/v1`)

Produced by Sprint 55, Phase 2's first sprint. Covers the `/api/v1` REST
API built over the completed, frozen backend (Sprints 44-54). See
`docs/architecture/BACKEND_ARCHITECTURE.md` for the backend itself — this
document covers only the HTTP layer added on top of it.

## 1. API Architecture

```
app/api/v1/
  router.py                 Aggregate APIRouter — includes every sub-router below
  routers/
    health.py                 GET /health, GET /ready
    version.py                 GET /version
    configuration.py            GET /configuration
    capabilities.py              GET /capabilities
    services.py                   GET /services
  schemas/
    common.py                  SuccessResponse, ErrorResponse, ValidationErrorResponse,
                                 PaginatedResponse, MetadataResponse
    system.py                    HTTP-layer schemas for the five system endpoints
  dependencies/
    state.py                    Every dependency provider — resolves from `request.app.state`
  exception_handlers/
    handlers.py                  Centralized exception -> HTTP response conversion
  middleware/
    request_id.py, timing.py, logging.py, registration.py
```

`app/api/intelligence/` (a pre-existing, unversioned API from an earlier
sprint) is untouched — both routers are mounted on the same `FastAPI`
application instance in `app/main.py`. `/api/v1` is purely additive.

**No business logic lives in this package.** Every route handler is a
thin translation: resolve an already-constructed service via dependency
injection, call exactly one of its existing methods, wrap the result in
`SuccessResponse`. No route recomputes, re-derives, or duplicates
anything a domain engine already computed.

## 2. Versioning Strategy

`/api/v1` is mounted with a prefix read from `APISettings.v1_prefix`
(`app/config/models.py`, already existed before this sprint) — not a
hardcoded string. A future `/api/v2` is a **sibling package**
(`app/api/v2/`, its own `router.py`, its own `routers/`/`schemas/`/
`dependencies/` as needed), mounted alongside `/api/v1` in `app/main.py`,
never a modification of `/api/v1` itself. Existing `/api/v1` consumers
are never broken by a `/api/v2` addition — this is what "future versions
must be extensible" means concretely in this codebase: additive routers
on the same `FastAPI` app, not in-place rewrites.

Endpoints that outgrow `/api/v1`'s behavior (a breaking response-shape
change, a removed field) belong in `/api/v2`, not a mutation of the
`/api/v1` handler — `/api/v1` is expected to remain stable once other
clients depend on it.

## 3. Response Conventions

Every successful `/api/v1` response is wrapped in one of two envelopes:

```json
// SuccessResponse[T]
{
  "data": { /* T — the actual payload, e.g. ApplicationHealth */ },
  "meta": {
    "request_id": "…",
    "timestamp": "2026-08-07T13:38:01.627983Z",
    "api_version": "v1"
  }
}
```

```json
// PaginatedResponse[T] — defined now, not yet used by any Sprint 55
// endpoint (none return a list); ready for the first list endpoint a
// future sprint adds.
{
  "data": [ /* T, T, ... */ ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "meta": { "...": "..." }
}
```

`meta.request_id` always matches the `X-Request-ID` response header (see
§6) — set by `RequestIDMiddleware` before the route handler runs, read by
`app.api.v1.schemas.common.request_id_of()` when building the response.
A handler exercised without the middleware installed (e.g. a unit test)
still gets a valid, freshly-generated id rather than an empty string.

Domain data itself is **never re-modeled** for HTTP — `/health` returns
`app.operations.health.models.ApplicationHealth` (Sprint 54) directly as
`data`, not a redundant HTTP-specific reshaping of the same fields. Only
`/version`, `/configuration`, `/capabilities`, and `/services` have their
own schemas (`app.api.v1.schemas.system`), because no existing domain
model represents "which capabilities does this deployment support" or
"what non-secret configuration is active" — those are genuinely new,
presentation-only shapes, not duplicated business logic.

## 4. Error Conventions

Every error response — a raised `HTTPException`, an unmatched route
(404), an unsupported method (405), a request validation failure (422),
an unhandled domain exception, or an unhandled internal error (500) — is
wrapped consistently:

```json
// ErrorResponse
{ "error": "not_found", "message": "...", "meta": { "...": "..." } }

// ValidationErrorResponse (422 only)
{
  "error": "validation_error",
  "message": "Request validation failed.",
  "details": [ { "location": ["query", "count"], "message": "...", "type": "..." } ],
  "meta": { "...": "..." }
}
```

`error` is a short, stable, machine-readable code:

| `error` | HTTP status | Trigger |
|---|---|---|
| `not_found` | 404 | Unknown route, or any `*NotFoundError` domain exception |
| `method_not_allowed` | 405 | Unsupported HTTP method on a known route |
| `service_unavailable` | 503 | A dependency provider found nothing configured on `app.state` |
| `conflict` | 409 | Any `Duplicate*Error`/`*AlreadyExists*`/`*AlreadyRegistered*` domain exception |
| `domain_error` | 400 | Any other exception from a domain package's own base exception class |
| `validation_error` | 422 | Request body/query/path parameter failed schema validation |
| `http_error` | (as raised) | Any other `HTTPException` |
| `internal_error` | 500 | Anything unhandled — the raw exception message is never returned to the client, only logged server-side |

**Domain exception mapping is registered per base class, not per
subclass.** Nine base exception classes are registered once each against
the same handler function (`AlertEngineError`, `BacktestingError`,
`ExplainabilityError`, `RecommendationEngineError`, `RiskAnalyticsError`,
`ScreeningError`, `SignalError`, `StrategyEngineError`,
`WatchlistServiceError`) — Starlette's exception dispatch walks each
exception's MRO, so every subclass (e.g. `RiskAssessmentNotFoundError`)
is caught by its package's registered base without a second registration.
The handler infers the HTTP status from the concrete exception class's
own **name** (`*NotFoundError` -> 404, `Duplicate*Error` -> 409, else
400) — a convention already consistent across every one of these
packages, so no hand-written per-subclass status map exists or needs
maintaining as new subclasses are added.

## 5. Dependency Injection

No new DI container exists. Every `app.api.v1.dependencies.state`
provider resolves an already-constructed component from `request.app
.state` — the exact same pattern `app.api.intelligence.dependencies`
(a pre-existing, earlier-sprint module) already established:

```python
def get_health_check_service(request: Request) -> HealthCheckService:
    return _resolve(request, "health_check_service", label="HealthCheckService")
    # raises HTTPException(503) if app.state.health_check_service is None
```

`get_repositories_map`/`get_services_map` return `dict[str, object | None]`
built from two constant name tuples (`REPOSITORY_NAMES`, `SERVICE_NAMES`)
mirroring exactly the `app.state` attribute names
`app.bootstrap.bootstrap_application_state` wires — reused, not
re-derived by inspecting attribute names at runtime.

**Testing uses `app.dependency_overrides`** — FastAPI's own standard
substitution mechanism, not a custom test container. In particular,
`tests/api/v1/conftest.py`'s shared `client` fixture overrides
`get_repositories_map` with fast, always-reachable fakes: the real
Postgres-backed repositories' own `health_check()` blocks for several
seconds each against an unreachable database in a sandboxed test
environment, and `/health`/`/ready` check all ten of them — genuinely
slow, not a bug in the endpoint itself. `tests/api/v1/test_health.py`
still exercises the real not-ready/unhealthy path deterministically, via
its own small, isolated probe app with a single fake *unhealthy*
repository.

## 6. Middleware

Registered in `app.api.v1.middleware.register_middleware`, in this
order (last registered = outermost = runs first on the way in):

1. **CORS** (`fastapi.middleware.cors.CORSMiddleware`) — origins from
   `APISettings.allowed_origins` (already existed).
2. **GZip** (`starlette.middleware.gzip.GZipMiddleware`) — compresses
   responses above 1 KB.
3. **Request logging** (`RequestLoggingMiddleware`) — logs one
   `LogCategory.APPLICATION` event per completed request via `app.state
   .structured_logger` (Sprint 54's `BaseStructuredLogger`) — a no-op if
   that isn't configured (e.g. a minimal test app).
4. **Timing** (`TimingMiddleware`) — sets the `X-Process-Time` response
   header; also records through `app.state.profiler`/`.metrics_recorder`
   (Sprint 54) when configured — reused, not a second timing/metrics
   implementation.
5. **Request ID** (`RequestIDMiddleware`, outermost, runs first) — reads
   an inbound `X-Request-ID` header or generates a UUID, sets `request
   .state.request_id`, echoes it back as a response header.

No authentication middleware is registered — see §7.

## 7. Future Authentication

Not integrated this sprint, by explicit constraint. When added:

- A new `app/api/v1/middleware/authentication.py` (or a FastAPI
  dependency, if per-route rather than blanket enforcement is preferred)
  slots into the same `register_middleware`/dependency chain — no
  existing middleware or route handler needs to change to accommodate it.
- `/health`, `/ready`, and `/version` should very likely remain
  unauthenticated (the conventional expectation for infrastructure
  probes); `/configuration`, `/capabilities`, and `/services` may or may
  not need to move behind auth depending on what's decided safe to expose
  publicly at that point.
- `CapabilitiesResponse.capabilities["authentication"]` already exists
  specifically so this exact moment — turning it `True` — is a one-line
  change once real auth lands, not a new endpoint.

## 8. Future Endpoint Expansion

> **Delivered by Sprint 57:** `/api/v1/watchlists` and `/api/v1/portfolio`
> — see `docs/architecture/WATCHLIST_PORTFOLIO_API.md`. The prediction
> below (written at Sprint 55 time) matches what was actually built:
> `PaginatedResponse[T]` went into use for the first time, and the nine
> already-registered domain exception base classes needed no new handler.
>
> **Delivered by Sprint 58:** the remaining six engines —
> `/api/v1/research`, `/screening`, `/signals`, `/alerts`, `/strategies`,
> `/backtests`, `/explainability` — plus completed OpenAPI Bearer
> security metadata across every protected endpoint. See
> `docs/architecture/INTELLIGENCE_API.md`.

Sprint 55 exposes only read-only introspection endpoints. The natural
next step is wrapping each domain engine's own service methods
(`PortfolioRecommendationService.generate_recommendations()`,
`RiskAnalyticsService.assess_portfolio()`, etc.) in CRUD-style routers —
following the exact same shape already established here:

- One `routers/<domain>.py` per engine, tagged distinctly in OpenAPI.
- Request/response schemas in `schemas/<domain>.py` — reusing each
  engine's own Pydantic domain models directly wherever they already fit
  the wire shape (mirrors `app.api.intelligence.schemas`'s own precedent
  of reusing `CompanyResearchReport` etc. directly), introducing a new
  HTTP-only schema only where no domain model represents the shape needed
  (mirrors this sprint's own `VersionResponse`/`ConfigurationResponse`).
- Dependency providers resolving each engine's service from `app.state`,
  exactly like `app.api.v1.dependencies.state` does for the read-only
  endpoints here.
- `PaginatedResponse[T]` (already defined, unused until now) is ready for
  the first `list_*`-backed endpoint (e.g. `GET /api/v1/watchlists`).
- The nine domain exception base classes already registered in
  `exception_handlers/handlers.py` mean a new CRUD endpoint that calls
  `RiskAnalyticsService.get_assessment()` and lets
  `RiskAssessmentNotFoundError` propagate needs **no new exception
  handler** — it is already converted to a 404 `ErrorResponse`
  automatically.
