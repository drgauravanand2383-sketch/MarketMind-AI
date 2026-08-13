# MarketMind AI — Release Checklist (RC1)

Produced by Sprint 60, the final planned backend/API sprint. Work
through this checklist before every production deployment from RC1
onward. This **extends** (does not replace) `deployment/RELEASE_CHECKLIST.md`
(Sprint 54's backend-only checklist, predating the API/WebSocket layer)
— run both; this one adds everything Sprints 55-60 introduced.

## 1. Configuration

- [ ] Every setting in `docs/release/PRODUCTION_CONFIGURATION_GUIDE.md`
      reviewed for this environment — not just present, but *correct*
      for this deployment (not a copy-pasted dev value).
- [ ] `ENVIRONMENT` set correctly (`production`/`staging`).
- [ ] `ALLOWED_ORIGINS` set to the real frontend origin(s) — not
      `localhost`.
- [ ] `SECURITY_HEADERS_HSTS_ENABLED=true` **only if** genuinely served
      over HTTPS end-to-end; left `false` otherwise.
- [ ] `SECURITY_HEADERS_CONTENT_SECURITY_POLICY` reviewed — if set,
      confirmed it doesn't break `/docs`/`/redoc` (or those are
      disabled for this environment).

## 2. Secrets

- [ ] `SECRET_KEY` changed from `change-me-in-production`.
- [ ] `POSTGRES_PASSWORD` changed from `change-me`.
- [ ] `ANTHROPIC_API_KEY` set (if company research/portfolio
      intelligence are needed for this deployment) or its absence is a
      deliberate choice, not an oversight.
- [ ] No secret committed to version control (`.env` is git-ignored;
      only `.env.example`'s placeholder values are tracked).
- [ ] `ConfigurationValidationService`'s startup warnings reviewed —
      every insecure-default warning is a deliberate choice for this
      environment, not an oversight.

## 3. Migrations

- [ ] `alembic upgrade head` completes without error against the target
      database.
- [ ] `alembic current` reports the expected head revision.
- [ ] Every table `app.operations.migrations.discovery.collect_table_names()`
      lists exists in the target database.
- [ ] Migrations run *before* deploying application code that depends on
      the new schema, never after.

## 4. Startup

- [ ] `bootstrap_application_state()` completes without raising.
- [ ] Structured startup log shows `bootstrap_completed` with
      `startup_validation_passed: true` (or every `false` reason is
      understood and acceptable for this environment — e.g. no
      ChromaDB in a deployment that doesn't need knowledge-hub features).
- [ ] `GET /ready` returns `200` once traffic is expected to be routed
      here.
- [ ] `GET /api/v1/health` reviewed — every repository/service this
      deployment actually needs reports reachable.

## 5. Shutdown

- [ ] A `SIGTERM` to the process completes `shutdown_application_state`
      and exits cleanly (verify locally: `tests/test_release_readiness.py::test_startup_and_shutdown_complete_without_raising`
      exercises this exact path).
- [ ] In-flight requests are allowed to drain before the process exits
      (orchestrator-level grace period configured — not something this
      application controls itself).
- [ ] `/ws` clients are expected to reconnect after a restart — confirm
      this is handled client-side (no server-side session resumption
      exists).

## 6. Testing

- [ ] `pytest tests` — zero failures, from a clean virtual environment
      matching `pyproject.toml`'s declared dependencies.
- [ ] `tests/operations/test_alembic_environment.py` passes.
- [ ] `tests/test_release_readiness.py` passes.
- [ ] `tests/performance/` passes (measure-only — a failure here means a
      catastrophic regression, not a missed optimization target).
- [ ] `tests/api/ws/test_rest_integration.py` passes (includes the full
      cross-domain workflow test).
- [ ] Total test count matches or exceeds the last known-good count
      (2700+ as of Sprint 60) — a lower count without an explicit,
      understood reason is itself a signal something was accidentally
      skipped/removed.

## 7. Documentation

- [ ] `docs/release/API_CONTRACT_V1.md` matches the actual deployed
      OpenAPI schema (regenerate the endpoint table if any endpoint was
      added/changed since RC1 — which, per the versioning policy, should
      only ever be additive).
- [ ] `docs/release/RELEASE_NOTES_RC1.md` (or this release's own notes,
      for a later release) accurately describes what's shipping.
- [ ] `docs/release/KNOWN_LIMITATIONS.md` still accurate — nothing fixed
      that's still listed, nothing new introduced that's missing.

## 8. OpenAPI

- [ ] `GET /openapi.json` returns `200` and parses as valid JSON.
- [ ] `components.securitySchemes.BearerAuth` present.
- [ ] Every non-public `/api/v1` operation's `security` field is
      `[{"BearerAuth": []}]`.
- [ ] Every operation has a unique `operationId`, a `summary`, and a
      `description`.
- [ ] Swagger UI (`/docs`) loads and its Authorize button works with a
      real token end-to-end.

## 9. Security

- [ ] `docs/release/SECURITY_CONSIDERATIONS.md` reviewed in full for
      this deployment.
- [ ] Security headers present on a real response
      (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
      `Permissions-Policy` — always; CSP/HSTS if enabled for this
      environment).
- [ ] TLS termination confirmed at the reverse proxy/load balancer (this
      application does not terminate TLS itself).
- [ ] Rate limiting and idempotency are **not** enforced by this
      application in RC1 — confirmed edge-level protection exists if
      this deployment is internet-facing (see `docs/release/SECURITY_CONSIDERATIONS.md`).

## 10. Performance

- [ ] `tests/performance/test_benchmarks.py` run against representative
      hardware for this deployment (the sandboxed CI/dev thresholds are
      deliberately loose — a real pre-production run against production-like
      infrastructure is worth doing at least once per release, even
      though this sprint's own scope is measure-only, not optimization).
- [ ] No individual benchmark regressed by an order of magnitude versus
      the previous release's own measured numbers (informal comparison
      — there is no automated performance-regression gate in RC1).

## 11. Clean environment verification

- [ ] No leftover throwaway virtualenvs, `__pycache__`, or
      `.pytest_cache` directories from the verification run committed or
      left on the deployment target.
- [ ] No stale `alembic_version` row from a different schema lineage on
      the target database.
- [ ] No development-only defaults remain unless this genuinely is a
      local/dev deployment.

## Sign-off

| Item | Status | Notes |
|---|---|---|
| Configuration reviewed | | |
| Secrets rotated/verified | | |
| Migrations applied | | |
| Startup verified | | |
| Shutdown verified | | |
| Tests executed (full suite, zero regressions) | | |
| Documentation verified | | |
| OpenAPI validated | | |
| Security reviewed | | |
| Performance benchmarked | | |
| Clean environment verified | | |

Record who ran this checklist, against which environment, and the date,
before promoting a build to production.
