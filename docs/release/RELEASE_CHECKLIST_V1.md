# MarketMind AI — Release Checklist (v1.0.0)

Produced by Milestone 10, the release-engineering milestone. This
**extends** `docs/release/RELEASE_CHECKLIST.md` (RC1, backend/API/
WebSocket) — run both; this one adds everything new for the full-stack
v1.0.0 release: the frontend, and cross-cutting release-engineering
items (CI/CD, Docker, full-stack security/docs).

## Verification log — 2026-08-13

This checklist was executed against the actual repository (commit
`f97311d`, working tree at the time of this run) rather than filled in
from documentation claims. Every item below is classified **PASS**
(independently reproduced), **BLOCKED** (a genuine defect was found;
either fixed and re-verified, or still open), **NOT VERIFIED**
(environment couldn't support the check), or **NOT APPLICABLE**.

**Environment**: Windows 11, native (non-Docker) execution.
- Backend: Python 3.14.4 (no Python 3.13 or `uv` installed on this
  machine; 3.14 satisfies `backend/pyproject.toml`'s `requires-python
  = ">=3.13"` pin, so a `.venv` + `pip install -e . --group dev` was
  used in place of `uv sync`). PostgreSQL/Redis/ChromaDB were **not**
  running (no Docker — see below), so backend verification exercised
  the app's own graceful-degradation path, not a fully-connected stack.
- Frontend: Node v24.16.0, npm 11.13.0 (CI pins Node 22; nothing in
  this run was Node-22-specific).
- **Docker: not installed on this machine** (`docker`/`docker compose`
  not found via Bash or PowerShell). Every Docker-dependent item below
  is marked NOT VERIFIED, with the closest available non-Docker
  equivalent noted.
- **No git remote configured** and no `gh` CLI available — actual
  GitHub Actions execution could not be checked. CI items are marked
  NOT VERIFIED for remote execution; workflow YAML was independently
  parsed and confirmed structurally valid.

**Defects found and fixed during this run** (see `git diff` for exact
changes; full detail in this session's completion report):
1. `GET /health`/`GET /ready` checked all ~10 Postgres-backed
   repositories **sequentially** — under a Postgres outage this took
   ~40s to respond, far exceeding `backend/Dockerfile`'s own shipped
   `HEALTHCHECK --timeout=5s`. Fixed: `HealthCheckService
   .check_repositories` now runs checks concurrently (`asyncio.gather`)
   — confirmed ~4.7s after the fix, same scenario. New regression test:
   `tests/operations/test_health.py::test_check_repositories_runs_concurrently_not_sequentially`.
2. `ConfigurationValidationService`/`StartupValidationService` checked
   `postgres.password` and `anthropic.api_key` for insecure placeholder
   defaults but never checked `AuthSettings.secret_key` — the JWT
   signing key — even though its own default
   (`"change-me-in-production"`, the literal value shipped in
   `.env.example`) was never in the insecure-default list at all. A
   production deployment that never overrides `SECRET_KEY` would pass
   every existing startup check while every JWT it issues is forgeable
   by anyone who has read the public `.env.example`. Fixed: `auth:
   AuthSettings` threaded through `validate()`/`validate_configuration()`
   /`validate_full()`/`_run_startup_validation()`, `"change-me-in-production"`
   added to `_INSECURE_DEFAULT_SECRETS`. New tests:
   `test_default_jwt_secret_key_flagged_as_insecure`,
   `test_real_jwt_secret_key_not_flagged`.
3. Frontend `npm run typecheck` had **17 real errors** (not zero, as
   §2/Milestone 9 claimed) across 12 files — Recharts v3 / react-hook-form
   v7.85 / zod v4 type-signature drift, an `exactOptionalPropertyTypes`
   violation, and one genuinely missing `describe()`/`switch` case.
   That last one is a real, reachable **runtime crash**, not just a
   type error: `DecisionHistoryEntry` has 7 `kind` variants but
   `decision-history-list.tsx`'s `describeEntry()` switch only handled
   5 — any user who ran a backtest or generated an explanation and then
   opened Decision History would hit
   `describeEntry()` returning `undefined`, then a destructuring
   `TypeError` crashing that panel. All 17 errors fixed (type-level
   fixes only, zero runtime-behavior change except the two missing
   switch cases, which now navigate to the correct existing routes).
   `npm run typecheck` and `npm run lint` are both zero-error/zero-warning
   again after the fix — confirmed by rerunning both, twice.

**Full-suite results this run**:
- Backend: `pytest tests` → **2803 passed, 0 failed** (2801 pre-existing
  + 2 new regression tests). `ruff check .` → 1966 findings (advisory,
  non-blocking per this project's own CI policy — documented baseline
  was ~1965; net change is line-shift noise from the fixes above, not
  new debt). `mypy app` (strict) → 126 errors in 56 files, **identical
  count before and after** every backend fix in this run — confirmed
  no regression. `python -m build` → sdist + wheel built cleanly
  (confirms the RC1 `readme` path fix still holds).
- Frontend: `npm run typecheck` → 0 errors (was 17). `npm run lint
  --max-warnings 0` → 0 errors/warnings (was 12, including 2 introduced
  and then fixed by an intermediate step in this same run — see
  completion report). `npm run test -- --run` → **402 passed, 0 failed**
  (1 failure on the full parallel run, `decision-workspace-page.test.tsx`,
  reproduced the project's own documented "transient flakiness under
  heavy parallel load" — reran in isolation and got 5/5 passed, so
  treated as environmental per this project's own established
  precedent, not a code defect). `npm run build` → succeeds; build
  output confirms the Recharts `CategoricalChart-*.js` core is still a
  separately-loaded chunk (Milestone 9's lazy-loading intact). `npm
  audit` → 0 vulnerabilities across 368 packages (matches
  `SECURITY_REVIEW_V1.md`).
- Backend security: `pip-audit` → 1 finding, `chromadb 1.5.9 /
  PYSEC-2026-311`, no fixed version available — exactly the finding
  `SECURITY_REVIEW_V1.md` documents, independently reproduced.

## 1. Backend verification

Unchanged from RC1 — work through `docs/release/RELEASE_CHECKLIST.md`
§1-11 in full. No backend business logic, API contract, or database
schema changed in this milestone.

- [ ] NOT VERIFIED — `docs/release/RELEASE_CHECKLIST.md` completed in
      full (out of scope for this run; that checklist requires a live
      Postgres, not available here).
- [x] PASS — `backend/pyproject.toml`'s `readme` fix verified:
      `python -m build` (no `uv` available in this environment) built
      an sdist and wheel with no "Readme path must be within the
      project directory" error.
- [x] PASS — `GET /api/v1/version` reports `"application_version":
      "1.0.0"` (confirmed against a natively-run instance without a
      real Postgres/Redis/ChromaDB — this endpoint has no such
      dependency).

## 2. Frontend verification

- [x] PASS (after fix) — `npm run typecheck` — zero errors. Was **17
      errors across 12 files** at the start of this run; all fixed
      (see verification log above), rerun confirmed clean.
- [x] PASS (after fix) — `npm run lint` — zero errors/warnings
      (`--max-warnings 0`). Was 12 errors across 5 files at the start
      of this run (2 in files touched by the typecheck fix, plus 3
      pre-existing in `company-table.test.tsx` unrelated to any change
      here); all fixed, rerun confirmed clean.
- [x] PASS — `npm run test` — 402 passed, 0 failed on the final run.
      One test failed on an earlier full-parallel run and was rerun in
      isolation per this item's own documented protocol — passed 5/5
      isolated, confirmed as this project's already-documented
      transient parallel-load flakiness (`MILESTONE_9.md` §8), not a
      regression.
- [x] PASS — `npm run build` — succeeds, produces `frontend/dist/`.
- [ ] NOT VERIFIED — a production build with `VITE_API_BASE_URL`/
      `VITE_WS_BASE_URL` unset throwing a clear console error requires
      opening the built `dist/index.html` in an actual browser; no
      browser-driven verification was performed this run (source-level
      behavior in `src/services/api/config.ts` was not re-audited here
      either — unchanged from prior verification).

## 3. API verification

Unchanged from RC1 — `docs/release/RELEASE_CHECKLIST.md` §8 (OpenAPI).
No endpoint added, removed, or changed in this milestone.

- [x] PASS — `docs/release/API_CONTRACT_V1.md` matches the live
      OpenAPI schema: confirmed 49 paths / 55 `/api/v1` operations
      against a running instance's own `/openapi.json`, exactly
      matching what `API_CONTRACT_V1.md` §1 itself documents. (Every
      other doc that stated the older pre-additive-extension "44
      paths, 50 operations" figure as a description of the *current*
      API surface — `ARCHITECTURE_OVERVIEW.md`, `DEPLOYMENT_GUIDE.md`,
      `KNOWN_LIMITATIONS.md`, `RELEASE_NOTES_V1.md`, and
      `API_CONTRACT_V1.md` §4 itself — has since been corrected to
      49/55 in a follow-up documentation-only pass. `RELEASE_NOTES_RC1.md`
      correctly keeps 44/50 — that is RC1's own actual historical
      count, before the three post-freeze additive extensions §1
      documents.)

## 4. WebSocket verification

Unchanged from RC1 — `docs/release/RELEASE_CHECKLIST.md` §4-5 cover
`/ws` indirectly via startup/shutdown. Additionally for this release:

- [ ] NOT VERIFIED — frontend-to-`/ws` live event verification requires
      a real backend + browser session; not performed this run.
      Partial equivalent: `/ws` was confirmed to reject an unauthenticated
      connection attempt with HTTP 403 (Python `websockets` client,
      no token) against a natively-run backend.
- [ ] NOT VERIFIED — reconnection-on-restart behavior requires a
      browser session; not performed this run.

## 5. Accessibility

Verified in Milestone 9, not re-audited from scratch here (no
accessibility-relevant code changed in this run either).

- [ ] NOT VERIFIED — not re-reviewed this run (no accessibility-relevant
      change made).
- [ ] NOT VERIFIED — keyboard-only spot-check requires a browser
      session; not performed this run.

## 6. Performance

- [x] PASS — `npm run build` output reviewed: `CategoricalChart-*.js`
      (Recharts core, ~303 kB raw / ~91 kB gzip) is its own
      separately-loaded chunk, confirmed not part of the eager entry
      graph.
- [ ] NOT VERIFIED — backend performance benchmarks (`RELEASE_CHECKLIST.md`
      §10) require a real Postgres-backed load test; not performed.
- [ ] NOT VERIFIED — frontend boot-timing marks require a browser
      session; not performed this run.

## 7. Security

- [x] PASS — `docs/release/SECURITY_REVIEW_V1.md` claims independently
      reproduced: `npm audit` (0 vulnerabilities / 368 packages) and
      `pip-audit` (exactly the documented `chromadb`/`PYSEC-2026-311`
      finding, nothing else) both match the document exactly.
- [ ] NOT VERIFIED — `docs/release/SECURITY_CONSIDERATIONS.md` (RC1)
      not re-reviewed line-by-line this run; spot-checked the security
      headers middleware and CORS wiring it describes (both match —
      see below).
- [x] PASS — `npm audit` — 0 vulnerabilities, reproduced.
- [x] PASS — `pip-audit` — 1 known finding (`chromadb` `PYSEC-2026-311`),
      reproduced; no fixed version exists yet. Mitigation
      (`docker-compose.prod.yml` not publishing ChromaDB's port) was
      read and confirmed present in the compose file, but its actual
      *runtime* effect (a running container with the port genuinely
      unreachable) could not be verified — no Docker.
- [x] PASS — backend security-headers middleware
      (`app/api/v1/middleware/security_headers.py`) sends
      `X-Content-Type-Options`/`X-Frame-Options`/`Referrer-Policy`/
      `Permissions-Policy`; `frontend/nginx.conf` sends the identical
      four headers. Verified by reading both, not by a live HTTP
      response (no running deployment) — the config-level match is
      exact.
- [x] PASS — no secret present anywhere in `frontend/`: `git ls-files`
      shows no tracked `.env` (only `.env.example`); repo-wide grep for
      `ANTHROPIC_API_KEY`/`SECRET_KEY`/`POSTGRES_PASSWORD` in
      `frontend/src` found only 2 comments naming (never reading) a
      setting; `import.meta.env` reads exactly 2 keys
      (`VITE_API_BASE_URL`/`VITE_WS_BASE_URL`), both non-secret URLs.
- [x] PASS (after fix) — JWT configuration: `AuthSettings.secret_key`
      is a `SecretStr` (never logged), CORS is wired to
      `settings.allowed_origins` with an explicit origin list (not
      `*`) even with `allow_credentials=True`. One genuine gap found
      and fixed — see defect #2 in the verification log above
      (the insecure-default JWT secret was never flagged by startup
      validation).

## 8. Documentation

- [x] PASS — full line-by-line accuracy review of the 5 guides against
      a live deployed system was not performed (no live deployment this
      run), but the one concrete inaccuracy spot-checked —
      `DEPLOYMENT_GUIDE.md`'s `GET /openapi.json | jq '.paths | keys |
      length'  # expect 44` — has been corrected to `# expect 49` in a
      follow-up documentation-only pass (see §3); everything else
      spot-checked (install steps, env var names, `alembic upgrade
      head` guidance) matched the actual repository structure.
- [x] PASS — `docs/architecture/ARCHITECTURE_OVERVIEW.md` reviewed;
      its "44 paths, 50 operations" figure has been corrected to 49/55.
- [x] PASS — `docs/release/RELEASE_NOTES_V1.md` reviewed; its "44
      paths, 50 operations" figure has been corrected to 49/55 to
      accurately describe what's in the tree at v1.0.0 (the additive
      extensions post-date RC1's own 44/50 snapshot).
- [x] PASS — `docs/release/KNOWN_LIMITATIONS.md` reviewed; its "50
      operations" references (the no-per-operation-`responses={}`
      limitation) have been corrected to 55 — still accurate otherwise;
      none of this run's findings are new *permanent* limitations (both
      backend defects were fixed; the frontend type errors were a
      verification gap, not a documented scope boundary).
- [ ] NOT APPLICABLE — no existing RC1 deployment being upgraded in
      this exercise.

## 9. Deployment

- [ ] NOT VERIFIED — Docker not installed on this machine; image
      builds could not be attempted. Dockerfiles were read and are
      structurally sound (multi-stage, non-root users, `HEALTHCHECK`
      directives present) — see the `/health` latency defect above for
      the one concrete issue that reading the Dockerfile surfaced.
- [ ] NOT VERIFIED — same as above.
- [ ] NOT VERIFIED — no Docker; full-stack compose-up not attempted.
      Closest equivalent performed: backend run natively (no Postgres/
      Redis/ChromaDB) to confirm graceful degradation, and frontend
      built + its dist output inspected.
- [ ] NOT VERIFIED — same; not attempted.
- [x] PASS — all three workflow YAML files parse as valid YAML
      (`.github/workflows/{backend,frontend}-ci.yml`, `release.yml`);
      job structure, `continue-on-error` advisory gates, and artifact
      naming all read as internally consistent with what they claim to
      do.
- [ ] NOT VERIFIED — no git remote configured in this environment and
      no `gh` CLI available; whether these workflows have ever actually
      executed successfully on GitHub could not be checked. **Do not
      treat YAML validity as equivalent to "CI passes."**
- [ ] NOT VERIFIED — no tag was pushed (out of scope — this run does
      not push, tag, or release per its own instructions).

## 10. Rollback plan

- **Backend**: redeploy the previous image/build. One schema change now
  ships with this release: migration `0002_auth_schema`, a release-blocking
  fix adding the Auth framework's tables (`auth_users`/`auth_roles`/
  `auth_revoked_tokens`), which were missing from `0001_baseline_schema`
  because `app.auth.repositories.postgres.models.Base` was never
  registered in `app.operations.migrations.discovery` — the Auth API
  could not function against a real Postgres database until this was
  fixed (see `docs/database/MIGRATIONS.md`). Rollback of this specific
  migration (`alembic downgrade 0001_baseline_schema`) is available and
  drops only the three auth tables, but is not recommended once any real
  user/role data exists in them — doing so simply reintroduces the
  original defect (Auth API non-functional against Postgres). Every
  other repository package's schema is unaffected either way.
- **Frontend**: since the frontend is a static artifact, rollback is
  redeploying the previous build's `dist/` output (or previous Docker
  image tag) — instantaneous, no data implications. If this is the
  *first* frontend deployment (adopting v1.0.0 from an RC1 backend-only
  deployment), "rollback" is simply taking the frontend back down; the
  backend is unaffected either way since the frontend has no
  server-side state of its own.
- **Both**: because the frontend and backend communicate only through
  the frozen `/api/v1`/`/ws` contract, the two can be rolled back
  independently without coordination — confirm this remains true for
  any *future* release before relying on it (a release that changes the
  contract would need both sides rolled back together).
- [ ] NOT VERIFIED — this plan was reviewed for internal consistency
      only; no actual rollback was rehearsed (would require a live
      deployment).

## Remaining blockers for v1.0.0 sign-off

None of the defects discovered this run are still open — both were
fixed and re-verified (see verification log). What remains **unverified**
(not blocked, just not exercisable in this environment) is entirely
Docker/browser/live-deployment/remote-CI dependent:

- Full Docker Compose production stack has never been built or started
  against this exact commit (no Docker in this environment).
- No browser-driven verification (WS live events, reconnection,
  keyboard-only accessibility spot-check, boot-timing marks, the
  unset-env-var console error) was performed.
- GitHub Actions workflows have not been confirmed to actually execute
  successfully on a real push/PR (no remote configured).
- `docs/release/RELEASE_CHECKLIST.md` (the RC1 backend checklist this
  document extends) was not run in full — it requires a live Postgres.

## Sign-off

| Item | Status | Notes |
|---|---|---|
| Backend verification | PARTIAL PASS | Tests/build/package verified natively; full RC1 checklist (needs live Postgres) not run |
| Frontend verification | PASS | typecheck/lint/test/build all verified after fixing 17 type errors + 1 runtime crash bug |
| API verification | PASS | Live OpenAPI schema matches `API_CONTRACT_V1.md` exactly |
| WebSocket verification | PARTIAL PASS | Auth rejection verified; live event delivery needs a browser + Docker |
| Accessibility | NOT VERIFIED | No browser session this run |
| Performance | PARTIAL PASS | Recharts chunking verified; backend benchmarks and boot-timing not verified |
| Security | PASS | npm audit / pip-audit / secrets / headers / CORS verified; JWT-secret validation gap found and fixed |
| Documentation | PASS | Reviewed; stale "44 paths, 50 operations" figures found in 4 docs (vs. live 49/55) and corrected in a follow-up documentation-only pass |
| Deployment | NOT VERIFIED | No Docker in this environment |
| Rollback plan reviewed | PARTIAL PASS | Internally consistent; not rehearsed live |

**Verification performed**: 2026-08-13, this repository's working tree
(commit `f97311d` + the fixes described in the verification log above,
uncommitted at the time this checklist was written).

**Sign-off (name, role, date)**: _— to be completed by a human owner
before promoting this build to production. This checklist documents
what was technically verified; it is not itself a release approval._
