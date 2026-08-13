# MarketMind AI — Intelligence API & OpenAPI Security (`/api/v1/research`, `/screening`, `/signals`, `/alerts`, `/strategies`, `/backtests`, `/explainability`)

Produced by Sprint 58, Phase 2. Exposes the remaining completed backend
engines — Company Research, Screening, Signal Detection, Alerts, Strategy
Evaluation, Backtesting, and Explainability — as authenticated REST APIs,
and completes OpenAPI authentication metadata (Bearer scheme, Swagger
Authorize button) across every protected endpoint in the application,
including the ones Sprint 55-57 already shipped. Read
`docs/architecture/API_ARCHITECTURE.md`,
`docs/architecture/AUTHENTICATION_ARCHITECTURE.md`, and
`docs/architecture/WATCHLIST_PORTFOLIO_API.md` first — this document only
covers what Sprint 58 adds on top.

## 1. OpenAPI Bearer security (cross-cutting)

`app/auth/dependencies/policy_guard.py`'s `require_policy()` now declares
an additional `Security(bearer_scheme)` sub-dependency, where
`bearer_scheme = HTTPBearer(scheme_name="BearerAuth", bearerFormat="JWT", auto_error=False)`.
This is the **only** change — it is purely additive to OpenAPI's generated
schema:

- `components.securitySchemes.BearerAuth` is now populated, which is what
  makes Swagger UI show the **Authorize** button.
- Every operation built from a route using
  `dependencies=[Depends(require_policy(...))]` now carries
  `"security": [{"BearerAuth": []}]` in its OpenAPI operation object —
  this applies retroactively to every Sprint 55-57 protected endpoint
  (`/watchlists/*`, `/portfolio/*`) with zero changes to those routers.

**No authentication or authorization logic changed or was duplicated.**
`auto_error=False` is essential: `HTTPBearer`'s default
(`auto_error=True`) would itself raise `403` for a missing
`Authorization` header, before `require_policy`'s own `principal is None`
check ever runs — breaking the existing "no token → 401" contract. With
`auto_error=False`, the `Security(bearer_scheme)` dependency resolves to
`None` silently on a missing/malformed header and its value is never even
read; real enforcement is still 100% `AuthenticationMiddleware` (resolves
`request.state.principal`) → `require_policy`'s 401/403 checks →
`PolicyEvaluator`, exactly as before Sprint 58.

## 2. Design decision: three domains have no persisted, id-addressable results

`Company Research`, `Screening`, and `Signal Detection` each have a spec'd
`GET .../{id}` endpoint, but their underlying services have no
persistence to back one:

- `CompanyResearchAgent` never writes anywhere (read-only, per its own
  module docstring) and `CompanyResearchReport` has no `id` field.
- `ScreeningEngine.evaluate_companies()` and
  `SignalDetectionService.evaluate_companies()` are synchronous, pure,
  stateless functions — no I/O, nothing persisted, no id.

This is unlike Risk/Recommendation (Sprint 57) or Backtesting/
Explainability (Sprint 58), which already have a full persisted
`*Request`/`*Result` flow with a real `get_result(id)`. Since this
sprint's spec explicitly prohibits modifying business logic, **by
explicit user decision**, a thin, generic, HTTP-layer-only cache —
`app.api.v1.schemas.result_store.InMemoryResultStore` — fills the gap for
all three domains:

- Lives entirely in the API layer (`app/api/v1/`), never touches
  `app/screening`, `app/signals`, or `app/agents/company_research`.
- Adds zero business logic — it only remembers a value under a freshly
  generated id (`put(value) -> id`) and looks it up (`get(id) -> value`,
  raising `ResultNotFoundError` → 404 via the same centralized
  `handle_domain_error`, registered separately from the nine real domain
  exception base classes to keep that invariant accurate — see
  `app/api/v1/exception_handlers/handlers.py`'s own docstring).
- **Known limitation:** in-process memory only. Cleared on restart, not
  shared across multiple app instances/workers. A future sprint should
  replace this with real repository-backed persistence in the owning
  domain package if multi-instance deployment requires it.
- Constructed in `app/main.py`'s `create_app()` (not `app/bootstrap.py`,
  since it isn't business logic and needs no async I/O to construct) as
  `app.state.research_report_store` / `.screening_result_store` /
  `.signal_result_store`.

## 3. Endpoint catalog

### Company Research (`/api/v1/research`)

| Method | Path | Permission | Delegates to |
|---|---|---|---|
| POST | `/research/company` | `research:run` | `CompanyResearchAgent.run()` (cached) |
| POST | `/research/batch` | `research:run` | `CompanyResearchAgent.run()` once per company, one shared `ExecutionContext` (cached) |
| GET | `/research/{request_id}` | `research:read` | `InMemoryResultStore.get()` |

### Screening (`/api/v1/screening`)

| Method | Path | Permission | Delegates to |
|---|---|---|---|
| GET | `/screening/profiles` | `screening:read` | `ScreeningEngine.list_profiles()` (+ in-memory `name` substring filter, Frontend Milestone 4) |
| POST | `/screening/profiles` | `screening:create` | `.create_profile()` |
| POST | `/screening/profiles/{profile_id}/duplicate` | `screening:create` | `.duplicate_profile()` (Frontend Milestone 4 — the method existed since this engine was first built, but was never reachable over REST until now) |
| PATCH | `/screening/profiles/{profile_id}` | `screening:update` | `.get_profile()` + `.update_profile()` (whole-object replace) |
| DELETE | `/screening/profiles/{profile_id}` | `screening:update` | `.delete_profile()` |
| POST | `/screening/run` | `screening:run` | `.get_profile()` + `.evaluate_companies()` (cached) |
| GET | `/screening/results/{result_id}` | `screening:read` | `InMemoryResultStore.get()` |

### Signal Detection (`/api/v1/signals`)

| Method | Path | Permission | Delegates to |
|---|---|---|---|
| GET | `/signals/definitions` | `signals:read` | `SignalDetectionService.list_signal_definitions()` |
| POST | `/signals/definitions` | `signals:update` | `.create_signal_definition()` |
| PATCH | `/signals/definitions/{definition_id}` | `signals:update` | `.get_signal_definition()` + `.update_signal_definition()` (whole-object replace) |
| DELETE | `/signals/definitions/{definition_id}` | `signals:update` | `.delete_signal_definition()` |
| POST | `/signals/evaluate` | `signals:evaluate` | `.get_signal_definition()` + `.evaluate_companies()` (cached) |
| GET | `/signals/results/{result_id}` | `signals:read` | `InMemoryResultStore.get()` |

### Alerts (`/api/v1/alerts`)

| Method | Path | Permission | Delegates to |
|---|---|---|---|
| GET | `/alerts` | `alerts:read` | `AlertService.list_alerts()` |
| GET | `/alerts/{alert_id}` | `alerts:read` | `.get_alert()` |
| POST | `/alerts/evaluate` | `alerts:evaluate` | `.get_rule()`/`.list_rules()` + `.evaluate_batch()` |

No rule-CRUD endpoint exists this sprint (not in scope) — `rule_ids`
supplied to `/alerts/evaluate` must reference already-existing
`AlertRule`s; empty means every enabled rule. `SignalResult`s are supplied
inline in the request body, since no endpoint (this sprint or any
earlier one) produces one server-side yet.

### Strategy Evaluation (`/api/v1/strategies`)

| Method | Path | Permission | Delegates to |
|---|---|---|---|
| GET | `/strategies` | `strategy:read` | `StrategyEvaluationService.list_strategies()` |
| POST | `/strategies` | `strategy:update` | `.create_strategy()` |
| PATCH | `/strategies/{strategy_id}` | `strategy:update` | `.get_strategy()` + `.update_strategy()` (whole-object replace) |
| DELETE | `/strategies/{strategy_id}` | `strategy:update` | `.delete_strategy()` |
| POST | `/strategies/evaluate` | `strategy:evaluate` | `PortfolioRecommendationService.get_result()` + `.evaluate_recommendations()` |
| GET | `/strategies/results/{result_id}` | `strategy:read` | `.get_evaluation()` |

The spec lists only three permissions for this domain (`read`/`update`/
`evaluate`) — create/update/delete all use `strategy:update`, matching
the spec's literal permission list. `result_id` is the evaluation
request's id (`StrategyEvaluationService` has no separate "result id"
concept). Evaluating needs an already-computed `RecommendationResult`
(fetched via `PortfolioRecommendationService`, reused from
`app.api.v1.portfolio.dependencies`) — `StrategyEvaluationService` has no
`create_request()` helper of its own (unlike Risk/Recommendation), so the
router builds the `StrategyEvaluationRequest` itself.

### Backtesting (`/api/v1/backtests`)

| Method | Path | Permission | Delegates to |
|---|---|---|---|
| POST | `/backtests` | `backtest:run` | `.create_request()` + `.run_backtest()` |
| GET | `/backtests/{run_id}` | `backtest:read` | `.get_run()` |
| GET | `/backtests/{run_id}/results` | `backtest:read` | `.get_result()` |

`{run_id}` is the `BacktestRequest.id` throughout — `BacktestRun` and
`BacktestResult` have no id of their own, each keyed by the request id
that produced it. `run_backtest()` is fully synchronous within the
request/response cycle (no background execution), so `POST /backtests`
runs the whole backtest and returns its result in one call.

### Explainability (`/api/v1/explainability`)

| Method | Path | Permission | Delegates to |
|---|---|---|---|
| POST | `/explainability` | `explainability:generate` | `.create_request()` + `.explain()` |
| GET | `/explainability/{request_id}` | `explainability:read` | `.get_result()` |

Mirrors the exact `create_request()` + generate-and-persist pattern
`POST /portfolio/recommendations` already established in Sprint 57.

## 4. Permission model

New permission strings introduced this sprint: `research:run`,
`research:read`, `screening:read`, `screening:create`,
`screening:update`, `screening:run`, `signals:read`, `signals:update`,
`signals:evaluate`, `alerts:read`, `alerts:evaluate`, `strategy:read`,
`strategy:update`, `strategy:evaluate`, `backtest:run`, `backtest:read`,
`explainability:generate`, `explainability:read`. Same convention as
Sprint 57's `watchlist:*`/`portfolio:*` — plain strings evaluated against
a principal's resolved permission set via `RequirePermission`, no inline
role/permission check anywhere, no registry of valid strings.

## 5. Error responses

Unchanged from Sprint 55 (`docs/architecture/API_ARCHITECTURE.md` §4). No
new domain exception handling was added for the six real domain packages
— `AlertEngineError`, `StrategyEngineError`, `BacktestingError`, and
`ExplainabilityError` were already registered against the centralized
`handle_domain_error` since Sprint 55. The one addition,
`ResultNotFoundError` (§2 above), reuses that same handler for a
consistent `404`/`not_found` shape without being folded into the
"nine domain exception base classes" invariant.

## 6. Testing

`tests/api/v1/{research,screening,signals,alerts,strategies,backtests,explainability}/`
— each a self-contained app (real `AuthenticationMiddleware` + real
`AuthenticationService`/`AuthorizationService` backed by in-memory
SQLite, real domain services each backed by their own in-memory SQLite
repository where applicable). `CompanyResearchAgent` is the only
substituted dependency (`StubCompanyResearchAgent` via
`app.dependency_overrides`, mirroring Sprint 57's
`StubPortfolioIntelligenceAgent`) since it would otherwise call the real
Claude API. Auth fixtures (`auth_repository`/`authorization_service`/
`auth_service`/`make_authenticated_headers`) are factored into one shared
module, `tests/api/v1/_auth_fixtures.py`, imported by every package's own
`conftest.py` instead of being duplicated seven times.

Covers per domain: 401/403 enforcement per permission, CRUD where
applicable, the execute/evaluate flow, 404/400 domain-exception mapping,
`extra="forbid"` validation. `tests/api/v1/test_openapi.py` additionally
covers the cross-cutting Bearer security metadata: `securitySchemes`
presence, and every `/api/v1` operation other than the unauthenticated
system/health probes carrying `security: [{"BearerAuth": []}]`.
