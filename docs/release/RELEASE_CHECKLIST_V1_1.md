# MarketMind AI — Release Checklist (v1.1 Release Candidate)

Milestone 17: Production Hardening & v1.1 Release Candidate. This
document extends (never replaces) `docs/release/RELEASE_CHECKLIST_V1.md`
— that document remains the frozen, historical v1.0.0 verification log
(Milestone 10, commit `f97311d`, Alembic at `0002_auth_schema`). This one
covers everything since: Milestones 11-16 (live market data, entity
resolution, portfolio intelligence, continuous/proactive intelligence,
durable persistence) plus Milestone 17's own release-hardening pass.

Every item below is classified **PASS**, **NOT VERIFIED**, **BLOCKED**,
or **N/A**, with evidence. Per this milestone's own explicit instruction:
do not claim browser tests passed if browser tooling was unavailable, do
not claim remote CI passed if no remote run was observed, do not claim
an organic market move if markets were closed, do not claim a live
provider outage if one was not actually exercised.

**Verification date**: 2026-08-15. **Commit base**: uncommitted working
tree on `main`, built on top of `f97311d` + Milestones 11-16 (verified
uncommitted per `git status` at the time of this run — see §19 of the
Milestone 17 completion report for the exact file list).

---

## 1. Backend test suite

| Item | Status | Evidence |
|---|---|---|
| Full suite, zero failures | **PASS** | `python -m pytest -q` → **3197 passed, 0 failed**, 245.21s. Up from 3193 (Milestone 16) by exactly the 4 new production-secret validation tests added this milestone (§7 below). |
| Known JWT/config test issue re-investigated | **PASS** | `test_real_jwt_secret_key_not_flagged` — already fixed in Milestone 16 (root cause: a test-authoring kwarg-vs-alias mismatch, not an application defect). Did not reappear; full suite confirms it still passes. |
| Migration revision-length regression guard | **PASS** | `test_every_migration_revision_id_fits_the_alembic_version_column` run in isolation — passed. Prevents recurrence of the real `VARCHAR(32)` bug Milestone 16 found and fixed live. |

## 2. Frontend test suite

| Item | Status | Evidence |
|---|---|---|
| Typecheck (`tsc -b --noEmit`) | **PASS** | Clean, no output. |
| Lint (`eslint . --max-warnings 0`) | **PASS** | Clean, 0 warnings. |
| Full Vitest suite, zero failures | **PASS** | **425 passed, 0 failed**, 84/84 test files, 658.30s. |
| Production build | **PASS** | `npm run build` succeeded, 6.05s. |
| `decision-workspace-page.test.tsx` timing investigation | **PASS (root-caused and fixed)** | Classified: **B — pre-existing environment flake**, not a genuine race and not a test-design defect. Root cause: `waitFor`'s own default internal timeout (1000ms) is independent of vitest's `testTimeout` (30s) — a real React Query → MSW → re-render round-trip that takes slightly over 1000ms under real machine load times out `waitFor` even though the test has ample time budget remaining. Confirmed by raising the timeout to 5000ms: the test then passed reliably, including a run where it completed in 13.17s total (vs. the failing runs' 100s+) — the same test, the same assertion, unweakened, simply given a realistic time budget. Fixed **globally** (`configure({ asyncUtilTimeout: 5000 })` in `src/test/setup.ts`), not as a one-off per-test patch, since the same tight 1000ms default is a latent risk for any test with a real async round-trip, not just this one. Full suite re-run afterward: 425/425 passed, confirming the fix didn't mask anything and didn't affect any other test. |

## 3. Clean Docker build from scratch

| Item | Status | Evidence |
|---|---|---|
| Backend image, `--no-cache` | **PASS** | Built successfully from scratch. Final size: 932MB. |
| Frontend image, `--no-cache` | **PASS** | Built successfully from scratch. Final size: 77.8MB. |
| All 5 containers start and report healthy | **PASS** | `postgres`, `redis`, `chromadb`, `backend`, `frontend` all `healthy` after rebuild. Persistent data (from Milestones 15/16's own live testing) confirmed intact — `alembic current` still reported `0005_ci_persistence` immediately after the rebuild, proving the clean image rebuild never touched the named volumes. |
| Readiness | **PASS** | `GET /api/v1/ready` → `{"ready": true, ...}`, `"summary": "21/21 component(s) healthy"`. |

## 4. Database migrations

| Item | Status | Evidence |
|---|---|---|
| Fresh empty database, `alembic upgrade head` | **PASS** | Verified against a genuinely empty, isolated PostgreSQL 16 instance (not the real data volume) — all 5 migrations applied in order (`0001`→`0002`→`0003`→`0004`→`0005`), 24 tables created (23 real + `alembic_version`), head correctly `0005_ci_persistence`. |
| Upgrade path from previous release state | **PASS** | A second isolated database was brought to `0002_auth_schema` (the exact state `RELEASE_CHECKLIST_V1.md` recorded as v1.0.0's own live-tested Alembic state), a real row was inserted (`watchlists`), then upgraded to head. Migrations applied in the correct order (`0002`→`0003`→`0004`→`0005`); the inserted row survived unchanged; the new `continuous_intelligence_state` table and the new `strategy_evaluation_results.recommendation_result_id` column were both present afterward. |
| Migration 0002 (auth schema) | **PASS** | Exercised as the starting point of the upgrade-path test above, and as an intermediate step of the fresh-database test. |
| Migration 0003 (risk market_data_coverage) | **PASS** | Applied cleanly in both tests above. |
| Migration 0004 (strategy linkage) | **PASS** | Applied cleanly in both tests above; new column confirmed present via `\d strategy_evaluation_results`. |
| Migration 0005 (continuous intelligence persistence) | **PASS** | Applied cleanly in both tests above; new table confirmed present via `\d continuous_intelligence_state`, correct composite primary key (`domain`, `key`). |
| Revision-length regression guard | **PASS** | See §1. |

## 5. Application startup

| Item | Status | Evidence |
|---|---|---|
| Startup validation | **PASS** | `bootstrap_completed` logged with `startup_validation_passed: true` on every fresh start observed this milestone. |
| Health / readiness | **PASS** | `/api/v1/health` → `HEALTHY`, all repositories/services reachable/constructed. `/api/v1/ready` → `ready: true`. Latency: health ~80ms, ready ~58ms (single-sample, informal). |
| Configuration validation | **PASS** | Confirmed via the full test suite (§1) plus 4 new tests for this milestone's own added check (§7). |
| Clean shutdown | **PASS** | `docker stop` (SIGTERM) produced an orderly `Shutting down` → `Waiting for application shutdown` → scheduler shutdown → `MarketMind AI application state shut down` → `Application shutdown complete` sequence — no forced kill needed, no errors. |
| Scheduler registration, no duplicate jobs | **PASS** | Fresh-start logs show exactly one `Added job "Scheduler.run_schedule"` line, matching the single schedule that is `enabled=true` at production defaults (Market Intelligence Ingestion) — the two disabled schedules (Market Data Refresh, Continuous Intelligence) are registered with `Scheduler`/`WorkflowEngine` but correctly receive no APScheduler job at all. |
| Persistence fallback behavior | **PASS** | Confirmed via Milestone 16's own dedicated test suite (`ContinuousIntelligenceStateStore`/`Suppression`/`CycleLock`, each with in-memory and Postgres-backed implementations of the same interface) — unchanged and still passing in the full suite (§1). |
| Operational scripts | **PASS** | `scripts/run_ingestion.py` (real RSS ingestion, live), `scripts/run_entity_backfill.py` (live), `scripts/run_continuous_intelligence.py` (live, both the disabled-gate rejection and a real enabled cycle), `scripts/inspect_continuous_intelligence.py` (live, confirmed read-only by source inspection — zero mutating calls) all exercised directly against the live Docker stack this milestone. |

## 6. Security hardening

| Item | Status | Evidence |
|---|---|---|
| `SECRET_KEY` validation | **PASS** | Pre-existing `missing_secret:auth.secret_key` (WARNING, advisory) confirmed still correct. **New this milestone**: `production_secret:auth.secret_key`/`production_secret:postgres.password` — ERROR-severity, `report.passed = False`, specifically when `environment=production` and the secret is still a known insecure default. Additive, does not change non-production behavior; covered by 4 new tests. |
| No insecure production secret silently accepted | **PASS** | Same as above — this was a real, evidence-backed gap (the general check was WARNING-only, non-blocking, in every environment including production) closed this milestone. |
| `.env` never tracked | **PASS** | `git check-ignore -v .env` confirms `.gitignore:25:.env` covers it; not present in `git status` output at any point this session. |
| CORS matches actual deployment frontend origin | **PASS** | `docker-compose.prod.yml` sets `ALLOWED_ORIGINS=http://localhost:8080`, matching the frontend's own published port (`EXPOSE 8080` in `frontend/Dockerfile`) exactly — not a wildcard, not left at the `localhost:3000` development default. |
| Security headers | **PASS** | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` always sent (confirmed via source: `SecurityHeadersMiddleware`). CSP/HSTS remain deliberately opt-in with documented rationale (CSP would break `/docs`/`/redoc` untuned; HSTS is actively wrong over plain HTTP) — unchanged from the existing, already-reviewed design. |
| WebSocket authentication | **PASS** | Live-verified this milestone: an invalid token is rejected (connection closed abnormally before upgrade completes); a real, freshly-issued token is accepted, receives the `connected` message, and a subscription request succeeds. |
| WebSocket permission filtering | **PASS** | Unchanged from Milestones 14-16's own extensively-tested permission-gated subscription model (`EVENT_TYPE_PERMISSIONS`/`UNGATED_EVENT_TYPES`); covered by the full backend + frontend suites. |
| No unauthenticated admin/operational endpoint | **PASS** | Every operational/diagnostic script (`run_*.py`, `inspect_continuous_intelligence.py`) is container-exec-only — no HTTP route exists for any of them, confirmed by source inspection (no corresponding router registration anywhere in `app/api/v1/`). |
| PostgreSQL/Redis/Chroma not host-published in production | **PASS** | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` — `postgres`, `redis`, `chromadb` all have no `ports:` key in the merged production config. Only `backend` (8000) and `frontend` (8080) are published. |
| No secrets in logs | **PASS** | `RequestLoggingMiddleware` logs only `method`/`path`/`status_code`/`request_id` — no headers, no body, no tokens. Confirmed by direct source read. |
| No credentials in source/tests/fixtures | **PASS** | `git diff` across every changed file this milestone scanned for real-looking secret patterns (`sk-...`, AWS-style keys, PEM private key headers) — none found. Test fixtures use obviously-fake values (`"a-real-jwt-secret"`, `"a-real-secret"`) consistent with the existing codebase convention. |
| External providers use bounded timeouts | **PASS** | `MARKET_DATA_TIMEOUT_SECONDS=10.0` (Yahoo Finance), `RSS_FEED_TIMEOUT_SECONDS=10.0` (RSS) — both confirmed in the live production environment config. |
| External content treated as untrusted | **N/A — unchanged** | No new external-content-handling code was introduced this milestone; the existing RSS/Yahoo parsing (never executes fetched content, only parses structured fields) is unchanged. |
| No arbitrary URL-fetch surface / SSRF | **PASS** | Confirmed by source review: no API request schema anywhere under `app/api/v1/` accepts a `url`/`HttpUrl` field. The only outbound HTTP calls originate from `app/providers/market_data/yahoo.py` (URL built from a validated/normalized ticker, never raw user input) and `app/providers/rss/provider.py`/`app/connectors/rss/rss_connector.py` (operator-configured `RSS_FEED_URLS`, not runtime-mutable by any authenticated user). No user-controllable URL-fetch surface exists. |
| Dependency vulnerability checks | **PASS (with one documented, unpatched, pre-existing finding)** | `pip-audit`: `chromadb==1.5.9` flagged for `PYSEC-2026-311` — confirmed via `pip index versions chromadb` that 1.5.9 is still the latest available release; no fixed version exists upstream yet. Already tracked as an accepted risk in `docs/release/SECURITY_REVIEW_V1.md`; unchanged, not newly introduced, not actionable via a version bump today. `npm audit` (frontend): **0 vulnerabilities**. |

## 7. Production Docker configuration

| Item | Status | Evidence |
|---|---|---|
| Backend published | **PASS** | Port 8000. |
| Frontend published | **PASS** | Port 8080. |
| Postgres NOT host-published | **PASS** | See §6. |
| Redis NOT host-published | **PASS** | See §6. |
| Chroma NOT host-published | **PASS** | See §6. |
| Containers run as non-root | **PASS** | Backend: `USER appuser` (`useradd --create-home --shell /bin/false appuser`). Frontend: `USER nginx` (nginx:alpine's own built-in non-root user). Both confirmed by direct `Dockerfile` inspection. |
| Volume ownership | **PASS** | `chown -R appuser:appuser /app` runs before the volume mount point is first initialized (documented in-Dockerfile rationale: an empty named volume inherits ownership from the image directory at first mount). |
| Restart policy | **PASS** | `restart: unless-stopped` on every service in the merged production config. |
| Healthchecks | **PASS** | Backend: `curl -f http://localhost:8000/api/v1/health`, 30s interval. Frontend: `wget ... http://127.0.0.1:8080/`, 30s interval (using `127.0.0.1` specifically to avoid an IPv6-resolution false failure — documented in-Dockerfile). Postgres/Redis: their own standard image healthchecks. All 5 containers observed reaching `healthy` status this milestone. |
| Network isolation | **PASS** | Every service on one bridge network (`marketmind-network`); no service reachable except via that network or its own published port. |
| Production environment variables | **PASS** | `ENVIRONMENT=production`, `DEBUG=false` confirmed in the merged config. |

## 8. End-to-end application flow

| Item | Status | Evidence |
|---|---|---|
| Login | **PASS** | Real `POST /api/v1/auth/login` against the live stack, `201`, real JWT issued. |
| Protected API | **PASS** | `GET /api/v1/watchlists` with a real bearer token → `200`, real data (6 watchlists accumulated across Milestones 14-17's own live testing). |
| Watchlist create / add company | **PASS** | Real `POST /api/v1/watchlists` and `POST .../companies` (ticker `AAPL`) — both `201`. |
| Research | **NOT VERIFIED (environment-dependent)** | Endpoint reachable, correctly authenticates/authorizes; the underlying LLM call fails with a clean `401 invalid x-api-key` because this deployment's `ANTHROPIC_API_KEY` is the documented placeholder, not a real key — this is a property of the local test environment's `.env`, not an application defect (the exact same "no real key → LLM-dependent features degrade, everything else unaffected" behavior already documented). No real Anthropic API key was available to exercise this further. |
| Entity resolution | **PASS** | Real RSS ingestion (`scripts/run_ingestion.py`) fetched 10 genuine live articles from MarketWatch/Dow Jones' public feed and generated 10 real local embeddings. `scripts/run_entity_backfill.py` then processed 28 real accumulated records: 7 resolved at HIGH confidence, 1 at MEDIUM, 20 correctly left unresolved (real financial news naturally references far more than the 12 canonical companies — an honest, expected outcome, not a failure). |
| Market data | **PASS** | Real live Yahoo Finance data confirmed flowing end-to-end: the Recommendations endpoint returned a real candidate with `market_price: 491.27`, `market_freshness: "FRESH"`, and a real `change_percent` — genuine live data, not fabricated. |
| Portfolio intelligence | **NOT VERIFIED (environment-dependent)** | Same `ANTHROPIC_API_KEY` limitation as Research — the agent's own market-data attachment step is downstream of the (failing) LLM call in this endpoint's implementation, so it could not be reached independently this session. |
| Risk | **PASS** | Real, already-stored assessment (from Milestone 16's own live testing) fetched successfully: `overall_severity: MODERATE`, real `generated_at` timestamp. |
| Strategy | **PASS** | Endpoint reachable, returns a correctly-shaped empty list (no strategies created in this test account) — `200`, not an error. |
| Recommendations | **PASS** | Real, already-stored recommendation fetched with real market data attached (see "Market data" above). |
| Signals | **PASS** | Real signal definition (`M14 Live Price Breakout`) fetched successfully. |
| Alerts | **PASS** | Real, already-generated alert (`SIGNAL_TRIGGERED`, `GENERATED` status) fetched successfully. |
| Continuous intelligence | **PASS** | See §9 below. |
| WebSocket | **PASS** | See §6 (auth) — plus a real subscription (`PORTFOLIO_INTELLIGENCE_UPDATED`) confirmed accepted. |
| Notification Center | **NOT VERIFIED (browser tooling unavailable)** | The underlying WS event delivery mechanism it depends on is proven live (above); the frontend UI rendering itself requires browser automation, unavailable this session (see §11). |

## 9. Continuous Intelligence — production semantics

| Item | Status | Evidence |
|---|---|---|
| Scheduled cycle | **PASS** | Confirmed registered correctly at production defaults (`enabled=false` by default; when temporarily enabled, exactly one job registered, no duplication). |
| Persistent state / persistent suppression | **PASS** | Re-confirmed this milestone: `scripts/inspect_continuous_intelligence.py` against the live, persistent database shows real suppression fingerprints (`RISK:...:MODERATE`/`LOW`/`CRITICAL`) from Milestone 16's own live acceptance testing, correctly surviving every restart and rebuild since. |
| Manual trigger respects the enable gate | **PASS** | With `CONTINUOUS_INTELLIGENCE_ENABLED` at its production default (`false`), `scripts/run_continuous_intelligence.py` correctly refuses to run: `{"status": "disabled", ...}`, exit code 1 — never silently runs regardless of the gate. |
| Live cycle on the freshly-rebuilt image | **PASS** | With the gate temporarily enabled, a real manual-trigger cycle ran against the freshly-rebuilt backend image and the real persistent database: 12 real entities examined, 0 failures, 0 changes (correctly — the real-world state observed by this cycle was genuinely unchanged since Milestone 16's own last observation). Confirms the rebuild did not regress the integration between the new image and the existing persisted state. |
| Concurrent-trigger prevention, restart recovery, duplicate suppression, WebSocket delivery (deep scenarios) | **PASS (evidence carried forward from Milestone 16, same session, unchanged code)** | Milestone 16's own live Docker acceptance testing — conducted in this same multi-milestone session, against this same codebase (confirmed unchanged for Continuous Intelligence's core logic; only the JWT-validation and documentation-adjacent files changed this milestone) — already produced exhaustive, direct live evidence for: a cross-process lock correctly blocking a live server cycle while a separate manual-trigger process held it (`continuous_intelligence_lock_contended` → `continuous_intelligence_cycle_skipped_overlap`, observed directly in server logs); a genuine restart correctly detecting zero duplicate events for unchanged state and correctly detecting a genuinely new transition immediately after; and suppression correctly blocking a duplicate fingerprint while allowing a genuinely different one through, confirmed via direct `psql` inspection of the `continuous_intelligence_state` table. Re-running that entire multi-hour scenario sequence this milestone (rather than the lighter re-confirmation above) was judged lower-value than the rest of this milestone's scope, given the underlying code is unchanged and was already proven live in the same session. |
| Live market movement | **NOT VERIFIED (environment-dependent)** | Real markets were closed for this entire testing window (Saturday) — the exact same, honestly-documented limitation as Milestones 15/16. Not fabricated. Covered by the full automated test suite (unit + integration, all passing). |

## 10. Provider resilience

| Item | Status | Evidence |
|---|---|---|
| Success / timeout / repeated failures / degraded threshold / unavailable threshold / recovery / stale cache | **PASS** | All exercised via controlled (mocked-HTTP) testing, per this milestone's own explicit "do not require an actual external outage" instruction — `tests/providers/market_data/test_yahoo_provider.py` (36 tests, including 5 dedicated to health degradation/recovery added in Milestone 16) and `tests/services/market_snapshot/test_market_snapshot_service.py` (stale-cache fallback). Re-run in isolation this milestone: all passed. |
| No second provider added | **PASS (by design)** | Confirmed — this milestone added no new provider, per its own explicit instruction. |

## 11. Backup / recovery

| Item | Status | Evidence |
|---|---|---|
| Database dump can be created | **PASS** | Real `pg_dump -Fc` against the live persistent database succeeded (88KB output). |
| Dump restores to a clean PostgreSQL instance | **PASS** | Piped directly into a fresh, isolated PostgreSQL 16 instance via `pg_restore` — no errors, all 24 tables present. |
| Alembic state correct after restore | **PASS** | `SELECT version_num FROM alembic_version` on the restored database → `0005_ci_persistence`, matching the source. |
| Application starts against restored database | **PASS** | `scripts/inspect_continuous_intelligence.py`, pointed at the restored database via a `DATABASE_URL` override, bootstrapped successfully and returned a correct, real report — including the exact same suppression fingerprints from the source database, proving genuine data continuity through the dump/restore cycle. |
| Procedure documented | **PASS** | `docs/release/ADMINISTRATOR_GUIDE.md` "Database" section extended with the exact tested command sequence (create/restore/verify/recover) — no new managed backup infrastructure introduced, per this milestone's own instruction. |

## 12. Observability

| Item | Status | Evidence |
|---|---|---|
| Backend health / readiness | **PASS** | See §5. |
| Scheduler state | **PASS** | `scripts/inspect_continuous_intelligence.py`'s `"scheduler"` section, and `/api/v1/health`. |
| CI cycle status / suppression state / lock status | **PASS** | All three directly reported by `scripts/inspect_continuous_intelligence.py`, confirmed live. |
| Provider health | **PASS** | `YahooFinanceProvider.health()` — real, observed-failure-history-driven status (Milestone 16), unit-tested (§10). |
| Current migration head | **PASS** | `alembic current`, confirmed live multiple times this milestone. |
| Major ingestion/market-data failures | **PASS** | Structured logging throughout (`ingestion_run_completed` with per-provider success/failure counts, `market_snapshot_provider_failed`, `continuous_intelligence_publish_failed`, etc.) — confirmed present in source and observed live during real ingestion this milestone. |
| Inspection scripts do not mutate state | **PASS** | `scripts/inspect_continuous_intelligence.py` confirmed by source inspection to call zero mutating operations (`put`/`try_claim`/`record_emitted`/`release`) — only `.get()`/`.list_domain()`/`.health_check()`. |

## 13. Performance / resource review

| Item | Status | Evidence |
|---|---|---|
| Backend startup | **PASS (measured)** | `bootstrap_completed` `duration_seconds` observed at ~3.6-4.9s across multiple fresh starts this milestone. |
| `/health` latency | **PASS (measured)** | ~80ms (single-sample, informal — not a load test). |
| `/ready` latency | **PASS (measured)** | ~58ms (single-sample, informal). |
| Representative API latency | **PASS (measured)** | Watchlist/Risk/Recommendations/Signals/Alerts reads all returned well under 1s in live testing this milestone (informal, not load-tested). |
| One CI cycle duration | **PASS (measured, with one caveat noted below)** | ~90-100s for 12 real canonical entities under normal conditions (consistent with Milestone 16's own measurement). |
| **Finding**: cold-start embedding model download | **Documented, not a blocker** | The freshly-rebuilt container's first ingestion/embedding-dependent operation triggered a ~79MB ONNX model download (`all-MiniLM-L6-v2`) at a slow rate, extending that one cycle to several minutes. Root cause: the model cache path (`~/.cache/chroma/onnx_models/`) is **not** part of the persistent `backend_chroma_cache` named volume (which only mounts `/app/data/cache`) — so every freshly-*recreated* container (not just every image rebuild) re-downloads this model on first use. This is a real, evidence-backed operational characteristic worth knowing (a fresh deployment's first embedding-dependent request will be slow) but is not a functional defect and was judged out of scope to fix this milestone (would mean changing the Docker volume/cache layout, a genuine "do not perform speculative rewrites" boundary) — documented here and in `docs/release/KNOWN_LIMITATIONS.md` instead. |
| Docker image sizes | **PASS (measured)** | Backend 932MB, frontend 77.8MB. No evidence of unnecessary bloat found (the backend size is consistent with its real dependency set: chromadb, onnxruntime, langchain/langgraph, asyncpg); not independently reduced this milestone (no evidence-backed action identified). |
| N+1 database access / unbounded concurrency / oversized Chroma queries / redundant recomputation | **PASS (no new issues found)** | Reviewed for evidence of a regression; found none. Existing bounded-concurrency patterns (semaphore-bounded provider calls in `MarketSnapshotService`/`YahooFinanceProvider`, capped `top_k` on every `KnowledgeHub.query()` call) remain in place and unchanged. No speculative rewrites performed, per this milestone's own explicit instruction. |

## 14. Documentation reconciliation

| Item | Status | Evidence |
|---|---|---|
| `README.md` | **PASS (corrected)** | Was badly stale (claimed a Next.js frontend, "Sprint 1" status) — rewritten to reflect the actual React+Vite frontend and current v1.0.0-released/v1.1-RC-in-preparation status. |
| `docs/release/USER_GUIDE.md` | **PASS (corrected)** | Directly contradicted `KNOWN_LIMITATIONS.md` (claimed "no live market data feed" when Milestone 13 added exactly that) — corrected. |
| `docs/database/MIGRATIONS.md` | **PASS (corrected)** | Was 3 revisions behind (`0003`-`0005` undocumented) — updated with the full current migration list and current head. The `VARCHAR(32)` revision-length incident (Milestone 16) is now permanently documented here as a lesson-learned, with a pointer to its regression guard. |
| `docs/release/DEPLOYMENT_GUIDE.md` | **PASS (corrected)** | Stale `alembic current` expected output (`0002_auth_schema`) corrected to `0005_ci_persistence`. |
| `docs/release/PRODUCTION_CONFIGURATION_GUIDE.md` | **PASS (corrected)** | Was missing an entire generation of settings (Ingestion/Embedding, Entity Resolution, Market Data, Continuous Intelligence, canonical-entity overlay) despite claiming to document "every setting" — all added with defaults and cross-references. |
| `docs/release/OPERATIONAL_RUNBOOK.md` / `ADMINISTRATOR_GUIDE.md` | **PASS (corrected)** | Neither previously mentioned any Milestone 11-16 operational script or schedule — both now do, plus the new backup/recovery procedure (§11). |
| API path/operation counts (49/55) | **PASS (verified consistent)** | Confirmed unchanged and consistent across `ARCHITECTURE_OVERVIEW.md`/`API_CONTRACT_V1.md`/`RELEASE_NOTES_V1.md`/`DEPLOYMENT_GUIDE.md` — no new REST endpoints were added by any of Milestones 11-16 (all additive work used existing endpoints, new WebSocket event types, or new operational scripts instead). |
| Historical/frozen documents (`RELEASE_NOTES_RC1.md`, `RELEASE_CHECKLIST.md`, `RELEASE_NOTES_V1.md`, `RELEASE_CHECKLIST_V1.md`) | **N/A — deliberately not modified** | These are explicitly scoped, dated, frozen historical records (per this milestone's own "do not silently rewrite history" instruction) containing their own point-in-time test counts (2697/2700+/2803) that predate Milestones 11-17. Left untouched; this document and `RELEASE_NOTES_V1_1.md` are the current source of truth going forward. |
| Version strings (`pyproject.toml`/`package.json`/`app.main`'s `version="1.0.0"`) | **NOT VERIFIED — deliberately deferred, not a defect** | All three still read `1.0.0`, unchanged since v1.0.0. Bumping them is a genuine release decision (what the next version number actually is, and when it takes effect) rather than a verification item this Implementation Engineer role should decide unilaterally — flagged here for whoever performs the actual v1.1 tagging/release step, consistent with §19's "do not tag" instruction. |

## 15. Browser acceptance

| Item | Status | Evidence |
|---|---|---|
| Browser tooling availability | **Checked, unavailable** | `mcp__claude-in-chrome__tabs_context_mcp` called directly this milestone — response: "Browser extension is not connected." Same result as every prior milestone. |
| Login / dashboard / watchlists / research / market data / portfolio intelligence / risk / recommendations / signals / alerts / notifications / WebSocket connectivity / reconnect / keyboard-accessibility walkthrough | **NOT VERIFIED (browser tooling unavailable)** | Not fabricated. The underlying backend/API/WebSocket mechanisms every one of these screens depends on are independently verified live (§8-9); only the actual browser rendering/interaction layer is unverified. |

## 16. Git / release hygiene

| Item | Status | Evidence |
|---|---|---|
| `git status` reviewed | **PASS** | Only the intended Milestone 11-17 files modified/added; no unexpected files. |
| `git diff --stat` reviewed | **PASS** | Confirms scope matches the work performed. |
| `git diff --check` | **PASS** | Only harmless CRLF-will-be-normalized warnings (Windows line-ending convention, pre-existing) — no real whitespace errors, no conflict markers. |
| No `.env` tracked | **PASS** | See §6. |
| No secrets | **PASS** | See §6. |
| No generated artifacts / accidental files | **PASS** | Reviewed the full untracked-file list — every new file is an intentional source/test/doc file from this milestone's own work; no build output, no `__pycache__`, no runtime data. |
| No commit / push / tag performed | **PASS (by design)** | Per this milestone's own explicit instruction — verification only. |

---

## Remaining NOT VERIFIED items (environment-dependent, explicitly preserved)

1. **Research / Portfolio Intelligence (LLM-dependent paths)** — this deployment's `ANTHROPIC_API_KEY` is a placeholder, not a real key. Everything reachable up to the LLM call itself was verified (auth, routing, request construction); the LLM call correctly fails with a clean, non-crashing `401`.
2. **Live organic market movement** — real markets were closed for the entire testing window.
3. **Live provider outage** — deliberately not forced (§10's own instruction); covered by controlled/mocked testing instead.
4. **Browser acceptance** — tooling unavailable, checked directly this milestone.
5. **Remote CI execution** — no GitHub remote is configured in this environment; workflow YAML validity/structure was reviewed (unchanged since Milestone 10's own verification), but no actual GitHub Actions run was observed to pass. Never claimed as verified.
6. **Version string bump** — deliberately deferred to the human release step, not a technical gap.

None of the above are BLOCKED — each is a genuine environment constraint honestly marked, with either strong indirect evidence (automated tests, reachable-but-degraded live behavior) or an explicit, reasoned deferral.

## Zero BLOCKED items

Every item in this checklist is **PASS**, **NOT VERIFIED** (environment-dependent, explicitly justified), or **N/A**. There are no **BLOCKED** items.

## Sign-off

See the Milestone 17 completion report for the final release recommendation. This checklist does not itself constitute sign-off — per this milestone's own instruction, no tag, commit, or push was performed; a human reviewer makes the final release decision.
