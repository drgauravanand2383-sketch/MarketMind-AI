# MarketMind AI — Watchlist & Portfolio API (`/api/v1/watchlists`, `/api/v1/portfolio`)

Produced by Sprint 57, Phase 2. Exposes the existing Watchlist Intelligence
Engine (`app.watchlist`), Risk Analytics Engine (`app.risk`), Portfolio
Recommendation Engine (`app.recommendations`), and Portfolio Intelligence
Agent (`app.agents.portfolio_intelligence`) as authenticated REST APIs,
built on top of the REST API Foundation (Sprint 55 —
`docs/architecture/API_ARCHITECTURE.md`) and the Authentication &
Authorization Framework (Sprint 56 —
`docs/architecture/AUTHENTICATION_ARCHITECTURE.md`). Read both first — this
document only covers what Sprint 57 adds on top.

## 1. Design decision: "portfolio" has no domain entity

This codebase has no `Portfolio` domain package or persisted "portfolio"
concept. By explicit product decision, **a `portfolio_id` is a
`watchlist_id`** — every portfolio view (`summary`, `intelligence`, `risk`,
`recommendations`) is computed on demand from that watchlist's current
tickers, by calling the relevant engine directly. No new "Portfolio"
model, table, or repository was introduced. `GET /api/v1/portfolio` and
`GET /api/v1/portfolio/{portfolio_id}` delegate straight to
`WatchlistService.list_watchlists()`/`.get_watchlist()` — the same data as
`/api/v1/watchlists`, exposed under a second, product-facing name.

## 2. Package layout

```
app/api/v1/
  watchlists/
    router.py          8 endpoints — thin delegation to WatchlistService
    schemas.py          CreateWatchlistRequest, RenameWatchlistRequest, AddCompanyRequest
    dependencies.py      get_watchlist_service (resolves app.state.watchlist_service)
  portfolio/
    router.py          7 endpoints — WatchlistService / RiskAnalyticsService /
                         PortfolioRecommendationService / PortfolioIntelligenceAgent
    schemas.py           GenerateRecommendationsRequest
    dependencies.py      get_risk_service, get_recommendation_service
                         (get_watchlist_service and get_portfolio_intelligence_agent
                          are reused directly from their existing modules, not duplicated)
  schemas/
    pagination.py        PaginationParams, paginate_items, build_paginated_response
    filters.py            WatchlistFilterParams, matches_watchlist_filters
```

No router computes anything a domain engine doesn't already compute.
Pagination and filtering are the one HTTP-layer-only concern: both apply
in-memory, after fetching each service's full `list_*()` result — the same
"thin HTTP-layer concern" precedent Sprint 55 established for its own
system endpoints, not a duplication of business logic.

## 3. Endpoint catalog

### Watchlists (`/api/v1/watchlists`)

| Method | Path | Permission | Delegates to |
|---|---|---|---|
| GET | `/watchlists` | `watchlist:read` | `WatchlistService.list_watchlists()` |
| POST | `/watchlists` | `watchlist:create` | `.create_watchlist()` |
| GET | `/watchlists/{watchlist_id}` | `watchlist:read` | `.get_watchlist()` |
| PATCH | `/watchlists/{watchlist_id}` | `watchlist:update` | `.rename_watchlist()` |
| DELETE | `/watchlists/{watchlist_id}` | `watchlist:delete` | `.delete_watchlist()` |
| POST | `/watchlists/{watchlist_id}/companies` | `watchlist:create` | `.add_company()` |
| DELETE | `/watchlists/{watchlist_id}/companies/{ticker}` | `watchlist:delete` | `.remove_company()` |
| GET | `/watchlists/{watchlist_id}/snapshot` | `watchlist:read` | `.generate_snapshot()` |

### Portfolio (`/api/v1/portfolio`)

| Method | Path | Permission | Delegates to |
|---|---|---|---|
| GET | `/portfolio` | `portfolio:read` | `WatchlistService.list_watchlists()` |
| GET | `/portfolio/{portfolio_id}` | `portfolio:read` | `WatchlistService.get_watchlist()` |
| GET | `/portfolio/summary?portfolio_id=` | `portfolio:read` | `WatchlistService.get_statistics()` |
| GET | `/portfolio/intelligence?portfolio_id=` | `portfolio:read` | `PortfolioIntelligenceAgent.run()` |
| GET | `/portfolio/risk?portfolio_id=` | `portfolio:read` | Most recent `RiskAssessment` for that `portfolio_id` (read-only) |
| GET | `/portfolio/recommendations?portfolio_id=` | `portfolio:read` | Most recent `RecommendationResult` for that `portfolio_id` (read-only) |
| POST | `/portfolio/recommendations` | `portfolio:recommend` | `PortfolioRecommendationService.create_request()` + `.generate_recommendations()` |
| GET | `/portfolio/{portfolio_id}/analysis-status` | `portfolio:read` | `InitialPortfolioAnalysisService.get_status()` — v1.2 Priority 8, read-only |
| POST | `/portfolio/{portfolio_id}/analysis` | `portfolio:recommend` | `InitialPortfolioAnalysisService.ensure_initial_analysis()` — v1.2 Priority 8, dispatched via `BackgroundTasks`, returns 202 immediately |

**Route ordering note:** `/summary`, `/intelligence`, `/risk`, and
`/recommendations` are registered *before* `/{portfolio_id}` in
`app/api/v1/portfolio/router.py`. FastAPI matches routes in registration
order, so registering `/{portfolio_id}` first would shadow every literal
sub-path (a request to `/portfolio/summary` would match
`/{portfolio_id}` with `portfolio_id="summary"` and fail UUID coercion,
rather than ever reaching the summary handler).

**Why `portfolio_id` is a query parameter, not a path parameter, on
`summary`/`intelligence`/`risk`/`recommendations`:** the sprint
specification defines these as flat paths (`GET /api/v1/portfolio/risk`,
not `GET /api/v1/portfolio/{portfolio_id}/risk`) — `portfolio_id` is
therefore accepted as a required query parameter on each.

**`analysis-status`/`analysis` (v1.2 Priority 8) use a path parameter
instead** (`/portfolio/{portfolio_id}/analysis-status`), matching
`GET /portfolio/{portfolio_id}` rather than the flat-path convention
above — no sprint constraint required the flat-path shape for these two
new endpoints, and a path parameter is the more conventional REST shape
for a single-resource action/status lookup. Both are two path segments
deep, so registration order relative to the single-segment `/{portfolio_id}`
route (and the flat literal routes) never matters — FastAPI resolves by
segment count/template, not registration order, once shapes actually
differ.

**"Most recent" for `/portfolio/risk` and `GET /portfolio/recommendations`:**
neither `RiskAssessment` nor `RecommendationResult` is looked up directly
by `portfolio_id` — each is linked only via its own `*Request` (
`RiskAssessmentRequest.portfolio_id`, `RecommendationRequest.watchlist_ids`).
The router lists every request, filters to ones matching `portfolio_id`,
and picks the one with the latest `created_at` before fetching its result.
If none match, the corresponding `*RequestNotFoundError` is raised (→ 404)
— no new domain exception was introduced for this case.

## 4. Authentication & authorization

Every endpoint requires an authenticated principal (`RequireAuthenticated`,
enforced implicitly — `require_policy` returns 401 whenever no principal
is present) and a specific policy-evaluated permission via
`RequirePermission("<permission>")`. No router performs an inline
role/permission check anywhere — see
`docs/architecture/AUTHENTICATION_ARCHITECTURE.md` §5 for how `Policy`
objects and `require_policy` work.

New permission strings introduced this sprint (none existed before):

`watchlist:read`, `watchlist:create`, `watchlist:update`,
`watchlist:delete`, `portfolio:read`, `portfolio:recommend`.

These are plain strings evaluated against a principal's resolved
permission set (`AuthorizationService`, RBAC with role hierarchy) — no
registry or enum of valid permission strings exists anywhere in the
codebase; adding a new protected endpoint elsewhere means picking a new
string and granting it via a `Role`, nothing more.

**Known gap:** no endpoint in this codebase — Sprint 57's or any earlier
sprint's — populates OpenAPI's `security` array. `require_policy` enforces
auth via a plain FastAPI `Depends`, not the `Security()`/`HTTPBearer`
scheme integration that would populate that field (and put an "Authorize"
button in Swagger UI). This is a pre-existing Sprint 56 auth-framework
design choice, not something Sprint 57 introduced or could fix without
touching the shared auth framework — flagged here rather than silently
left undocumented. Actual enforcement (401/403) is correct and fully
tested regardless.

## 5. Pagination

`GET /watchlists` and `GET /portfolio` both accept:

| Param | Default | Constraint |
|---|---|---|
| `page` | 1 | `>= 1` |
| `page_size` | 20 | `1..100` |
| `sort` | none | must be one of `name`, `created_at`, `updated_at` — else 422 |
| `direction` | `asc` | `asc` or `desc` |

Response is `PaginatedResponse[Watchlist]` (Sprint 55's envelope, defined
but unused until this sprint):

```json
{
  "data": [ /* Watchlist, Watchlist, ... */ ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "meta": { "request_id": "...", "timestamp": "...", "api_version": "v1" }
}
```

## 6. Filtering

`GET /watchlists` and `GET /portfolio` both accept these query filters
(all optional, combinable with AND):

| Param | Matches |
|---|---|
| `sector`, `country`, `theme`, `ticker`, `company` | At least one item in the watchlist matches **all** active item-level filters |
| `name` | Case-insensitive substring match against the watchlist's own `name` (Frontend Milestone 3 addition — the only watchlist-level, non-item, non-date filter) |
| `created_after`, `created_before` | The watchlist's own `created_at`; 422 if `created_after > created_before` |

## 7. Validation

- Path/query identifiers typed `uuid.UUID` → automatic 422 on malformed
  input (chosen over a hand-written validator, per Sprint 55/56 precedent).
- Ticker path parameter (`DELETE .../companies/{ticker}`) constrained by
  `Path(..., pattern=r"^[A-Za-z0-9.\-]{1,10}$")` → 422 on invalid format.
- Every request schema uses `model_config = ConfigDict(extra="forbid")` →
  422 on unknown fields.
- `POST /watchlists/{id}/companies` uses a dedicated `AddCompanyRequest`,
  **not** `app.watchlist.models.WatchlistItem` directly — `WatchlistItem`
  has a required `added_at: datetime` field that is server-assigned
  bookkeeping, not something a client should supply. The router constructs
  the full `WatchlistItem` itself, setting `added_at` from the current
  server time.

## 8. Error responses

Unchanged from Sprint 55 (`docs/architecture/API_ARCHITECTURE.md` §4). No
new exception classes or handlers were added — `WatchlistServiceError`,
`RiskAnalyticsError`, and `RecommendationEngineError` were already
registered against the centralized `handle_domain_error` since Sprint 55,
so every domain exception these services raise (`WatchlistNotFoundError` →
404, `DuplicateTickerError` → 409, `WatchlistValidationError` → 400, etc.)
propagates from a Sprint 57 router with zero manual `try/except`.

## 9. Example requests

```
POST /api/v1/watchlists
Authorization: Bearer <token>
{ "name": "Tech Growth", "description": "High-growth technology companies." }

→ 201
{ "data": { "id": "...", "name": "Tech Growth", "items": [], ... }, "meta": { ... } }
```

```
POST /api/v1/watchlists/{watchlist_id}/companies
{ "ticker": "aapl", "company_name": "Apple", "sector": "Technology" }

→ 201  (ticker normalized to "AAPL"; added_at set server-side)
```

```
GET /api/v1/portfolio/risk?portfolio_id={watchlist_id}

→ 200 { "data": { "request_id": "...", "overall_risk_score": 57.14, ... }, "meta": { ... } }
→ 404 { "error": "not_found", "message": "No risk assessment request found with id '...'." }
```

```
POST /api/v1/portfolio/recommendations
{
  "portfolio_id": "...",
  "evidence": [ { "ticker": "AAPL", "sector": "Technology" } ],
  "max_recommendations": 5
}

→ 201 { "data": { "request_id": "...", "total_candidates": 1, "recommendations": [...] }, "meta": { ... } }
```

## 10. Portfolio Intelligence agent wiring (bootstrap change)

`GET /portfolio/intelligence` calls the existing
`PortfolioIntelligenceAgent`. Its dependency-injection chain was
pre-existing but broken — independent of this sprint's router work,
`app/api/intelligence/dependencies.py`'s `get_company_research_agent`/
`get_portfolio_intelligence_agent` passed keyword arguments neither
constructor accepts (`knowledge_repository` instead of `knowledge_hub`;
`llm_service`/`prompt_registry` missing entirely), and neither
`LLMService`, `PromptRegistry`, nor `KnowledgeHub` was ever constructed or
attached to `app.state` in `app/bootstrap.py`. This was fixed (by explicit
user decision, since it's infrastructure wiring beyond router-only scope)
rather than left blocked:

- `app/bootstrap.py` gained four new `build_*` functions:
  `build_prompt_registry()` (always succeeds — registers every agent's
  templates), `build_knowledge_hub(knowledge_repository)` (thin wrapper,
  `None` if no repository), `build_llm_service(logger)` (constructs a real
  Claude-backed `LLMService` from `AnthropicSettings`/`LLMSettings`;
  degrades to `None` — never crashes startup — if `ANTHROPIC_API_KEY` is
  unset, mirroring every other fallible `build_*` function's convention),
  and `build_company_research_agent`/`build_portfolio_intelligence_agent`
  (each `None` if any required dependency is unavailable).
- `app.state.prompt_registry`, `.knowledge_hub`, `.llm_service`,
  `.company_research_agent`, and `.portfolio_intelligence_agent` are now
  wired in `bootstrap_application_state`.
- `app/api/intelligence/dependencies.py`'s `get_company_research_agent`/
  `get_portfolio_intelligence_agent` now resolve from `app.state` (the
  same pattern every other provider in that module already used) instead
  of incorrectly constructing an agent per-request.
- This also fixes the pre-existing, unversioned `POST /portfolio/research`
  endpoint (`app/api/intelligence/router.py`), which shared the same
  broken DI chain and would have raised `TypeError` at request time before
  this fix.

Without a configured `ANTHROPIC_API_KEY`, `/portfolio/intelligence` and
`/portfolio/research` both return 503 (`PortfolioIntelligenceAgent is not
configured on this application instance.`) rather than crashing the
application at startup.

## 11. Testing

`tests/api/v1/watchlists/` and `tests/api/v1/portfolio/` — each a
self-contained app (real `AuthenticationMiddleware` + real
`AuthenticationService`/`AuthorizationService` backed by in-memory SQLite,
real `WatchlistService`/`RiskAnalyticsService`/`PortfolioRecommendationService`
each backed by their own in-memory SQLite repository). No mocks except
`PortfolioIntelligenceAgent`, substituted via `app.dependency_overrides`
(the same test-substitution mechanism Sprint 55 already established) since
it would otherwise call the real Claude API. Covers: 401/403 enforcement
per permission, full CRUD, filtering, pagination bounds, sort validation,
ticker format validation, `extra="forbid"` rejection, domain-exception →
HTTP status mapping (404/409), "most recent" lookup correctness, 503 when
a dependency is unconfigured, and OpenAPI tag/schema presence.
`tests/test_bootstrap.py` covers the five new `build_*` functions,
including the `ANTHROPIC_API_KEY`-unset degradation path.
